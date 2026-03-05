import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict
from uuid import uuid4

import httpx
from langgraph.graph import END, StateGraph

from app.agents import AgentTool, ToolContext, ToolRegistry, ToolResult
from app.config import settings
from app.note import NoteService, TaskPriority
from app.repositories import KnowledgeItemRepository
from app.services.llm_service import LLMService
from app.services.reminder_service import ReminderService
from app.services.vector_store import VectorStore
from app.utils import logger

ActionName = Literal[
    "create_reminder",
    "update_latest_reminder_recurrence",
    "delay_latest_reminder",
    "skip_next_reminder",
    "pause_latest_reminder_until",
    "check_reminders_status",
    "list_workday_reminders",
    "write_idea",
    "write_task",
    "write_note",
    "search_memory",
    "web_search",
    "write_logseq_doc",
    "answer",
]


@dataclass
class AgentOutcome:
    success: bool
    response: str


class AgentState(TypedDict, total=False):
    run_id: str
    user_id: str
    provider: str
    text: str
    channel_id: int | None
    steps: int
    max_steps: int
    thought: str
    action: ActionName | None
    action_input: dict[str, Any]
    observation: str
    scratchpad: list[str]
    last_reminder_id: int | None
    last_reminder_content: str
    done: bool
    response: str


class CognitiveAgentService:
    def __init__(
        self, note_service: NoteService | None = None, llm_service: LLMService | None = None
    ) -> None:
        self.note_service = note_service or NoteService()
        self.llm_service = llm_service or LLMService()
        self.vector_store = VectorStore()
        self.knowledge_repo = KnowledgeItemRepository()
        self._tool_registry = self._build_tool_registry()
        self._session_slots: dict[str, dict[str, Any]] = {}
        self._graph = self._build_graph()

    @staticmethod
    def _session_key(user_id: str, provider: str) -> str:
        return f"{provider}:{user_id}"

    def _build_graph(self):
        builder = StateGraph(AgentState)
        builder.add_node("plan", self._plan_node)
        builder.add_node("act", self._act_node)
        builder.add_node("judge", self._judge_node)
        builder.set_entry_point("plan")
        builder.add_conditional_edges(
            "plan",
            self._plan_router,
            {
                "act": "act",
                "end": END,
            },
        )
        builder.add_edge("act", "judge")
        builder.add_conditional_edges(
            "judge",
            self._judge_router,
            {
                "plan": "plan",
                "end": END,
            },
        )
        return builder.compile()

    @staticmethod
    def _plan_router(state: AgentState) -> str:
        if state.get("done"):
            return "end"
        return "act"

    @staticmethod
    def _judge_router(state: AgentState) -> str:
        if state.get("done"):
            return "end"
        return "plan"

    async def run(
        self, user_id: str, provider: str, text: str, channel_id: int | None = None
    ) -> AgentOutcome:
        if not settings.agent_enabled:
            return AgentOutcome(False, "")

        session_key = self._session_key(user_id=user_id, provider=provider)
        slot = self._session_slots.get(session_key, {})
        run_id = str(uuid4())
        state: AgentState = await self._graph.ainvoke(
            {
                "run_id": run_id,
                "user_id": user_id,
                "provider": provider,
                "text": text.strip(),
                "channel_id": channel_id,
                "steps": 0,
                "max_steps": settings.agent_max_steps,
                "scratchpad": [],
                "last_reminder_id": slot.get("last_reminder_id"),
                "last_reminder_content": slot.get("last_reminder_content", ""),
                "done": False,
            }
        )
        self._session_slots[session_key] = {
            "last_reminder_id": state.get("last_reminder_id"),
            "last_reminder_content": state.get("last_reminder_content", ""),
        }
        response = state.get("response", "").strip()
        await self._append_trace(
            {
                "type": "run_end",
                "run_id": run_id,
                "user_id": user_id,
                "provider": provider,
                "steps": state.get("steps", 0),
                "done": bool(state.get("done", False)),
                "response": response,
            }
        )
        if not response:
            return AgentOutcome(False, "我还没想好怎么处理这条输入，请换个说法试试。")
        return AgentOutcome(True, response)

    async def _plan_node(self, state: AgentState) -> AgentState:
        steps = int(state.get("steps", 0))
        max_steps = int(state.get("max_steps", 4))
        if steps >= max_steps:
            await self._append_trace(
                {
                    "type": "plan_stop",
                    "run_id": state.get("run_id", ""),
                    "reason": "max_steps_reached",
                    "steps": steps,
                }
            )
            return {
                **state,
                "done": True,
                "response": state.get("response", "") or "已达到最大步骤，先到这里。",
            }

        scratchpad = state.get("scratchpad", [])
        prompt = self._planner_prompt(
            state=state,
            user_text=state.get("text", ""),
            provider=state.get("provider", ""),
            scratchpad=scratchpad,
        )
        try:
            raw = await self.llm_service.chat_with_system(
                system_prompt=prompt["system"],
                user_message=prompt["user"],
                temperature=0.0,
                max_tokens=settings.agent_planner_max_tokens,
                model=self._agent_model(),
                base_url=settings.intent_base_url or None,
                api_key=settings.intent_api_key or None,
            )
            plan = self._extract_json(raw)
        except Exception as e:
            logger.warning(f"Agent planner failed: {e}")
            return {
                **state,
                "done": True,
                "response": "暂时无法完成复杂处理，已记录你的输入。",
            }

        done = bool(plan.get("done", False))
        action = plan.get("action")
        action_input = plan.get("action_input") or {}
        thought = str(plan.get("thought", "")).strip()
        response = str(plan.get("response", "")).strip()

        if done:
            await self._append_trace(
                {
                    "type": "plan_done",
                    "run_id": state.get("run_id", ""),
                    "thought": thought,
                    "response": response,
                    "steps": steps + 1,
                }
            )
            return {
                **state,
                "done": True,
                "response": response or "处理完成。",
                "thought": thought,
                "steps": steps + 1,
            }

        if action not in self._available_actions():
            fallback = self._fallback_action_from_text(state.get("text", ""))
            if fallback is not None:
                await self._append_trace(
                    {
                        "type": "plan_fallback_action",
                        "run_id": state.get("run_id", ""),
                        "invalid_action": action,
                        "fallback_action": fallback["action"],
                        "steps": steps + 1,
                    }
                )
                return {
                    **state,
                    "action": fallback["action"],
                    "action_input": fallback["action_input"],
                    "thought": f"invalid_action_fallback: {fallback['thought']}",
                    "steps": steps + 1,
                }
            await self._append_trace(
                {
                    "type": "plan_invalid_action",
                    "run_id": state.get("run_id", ""),
                    "action": action,
                    "steps": steps + 1,
                }
            )
            return {
                **state,
                "done": True,
                "response": response or "我没法确定下一步动作，先按普通记录处理。",
                "steps": steps + 1,
            }

        return {
            **state,
            "action": action,
            "action_input": action_input,
            "thought": thought,
            "steps": steps + 1,
        }

    async def _act_node(self, state: AgentState) -> AgentState:
        action = state.get("action")
        payload = state.get("action_input", {})

        observation = ""
        try:
            if action == "answer":
                return {
                    **state,
                    "done": True,
                    "response": str(payload.get("text", "")).strip() or "处理完成。",
                }

            context = ToolContext(
                run_id=state.get("run_id", ""),
                user_id=state.get("user_id", ""),
                provider=state.get("provider", ""),
                text=state.get("text", ""),
                channel_id=state.get("channel_id"),
                state=state,
            )
            result = await self._tool_registry.execute(str(action), context, payload)
            observation = result.observation
        except Exception as e:
            observation = f"tool_error: {e}"

        scratchpad = list(state.get("scratchpad", []))
        scratchpad.append(
            json.dumps(
                {
                    "action": action,
                    "input": payload,
                    "observation": observation,
                },
                ensure_ascii=False,
            )
        )
        await self._append_trace(
            {
                "type": "tool_call",
                "run_id": state.get("run_id", ""),
                "step": state.get("steps", 0),
                "action": action,
                "input": payload,
                "observation": observation,
            }
        )
        return {
            **state,
            "observation": observation,
            "scratchpad": scratchpad,
        }

    async def _judge_node(self, state: AgentState) -> AgentState:
        action = state.get("action")
        observation = state.get("observation", "")
        steps = int(state.get("steps", 0))
        max_steps = int(state.get("max_steps", 4))

        terminal_ok_prefix = (
            "reminder_created:",
            "reminder_recurrence_updated:",
            "reminder_delayed:",
            "reminder_skipped:",
            "reminder_paused:",
            "reminder_status:",
            "workday_reminders:",
            "idea_written",
            "task_written:",
            "note_written",
            "logseq_doc_written",
        )
        terminal_error_prefix = (
            "parse_reminder_failed",
            "delay_minutes_missing",
            "reminder_delay_no_recent",
            "reminder_skip_no_recent",
            "pause_until_missing",
            "reminder_pause_no_recent",
            "tool_error:",
            "unknown_action",
            "write_doc_missing_title",
        )
        terminal_error_immediate = {
            "delay_minutes_missing",
            "reminder_delay_no_recent",
            "reminder_skip_no_recent",
            "pause_until_missing",
            "reminder_pause_no_recent",
        }

        if observation.startswith(terminal_ok_prefix):
            response = self._format_terminal_response(action, observation)
            await self._append_trace(
                {
                    "type": "judge_done",
                    "run_id": state.get("run_id", ""),
                    "reason": "terminal_tool_success",
                    "action": action,
                    "observation": observation,
                    "response": response,
                }
            )
            return {
                **state,
                "done": True,
                "response": response,
            }

        if observation.startswith(terminal_error_prefix) and steps >= max_steps - 1:
            response = "我尝试了多步处理但仍失败，请换个说法或补充更多信息。"
            await self._append_trace(
                {
                    "type": "judge_done",
                    "run_id": state.get("run_id", ""),
                    "reason": "terminal_error_and_budget_exhausted",
                    "action": action,
                    "observation": observation,
                    "response": response,
                }
            )
            return {
                **state,
                "done": True,
                "response": response,
            }

        if observation in terminal_error_immediate:
            response = self._format_terminal_response(action, observation)
            await self._append_trace(
                {
                    "type": "judge_done",
                    "run_id": state.get("run_id", ""),
                    "reason": "terminal_error_immediate",
                    "action": action,
                    "observation": observation,
                    "response": response,
                }
            )
            return {
                **state,
                "done": True,
                "response": response,
            }

        await self._append_trace(
            {
                "type": "judge_continue",
                "run_id": state.get("run_id", ""),
                "action": action,
                "observation": observation,
                "steps": steps,
            }
        )
        return state

    def _planner_prompt(
        self, state: AgentState, user_text: str, provider: str, scratchpad: list[str]
    ) -> dict[str, str]:
        tools = [tool.usage for tool in self._tool_registry.list_tools()] + ["answer(text)"]
        system = (
            "你是 CognitiveOS 的认知代理。目标是通过多步工具调用完成用户任务。"
            "每一步必须输出严格 JSON: "
            '{"done":bool,"thought":str,"action":str,"action_input":{},"response":str}。'
            "done=true 时可直接返回最终 response。"
            "done=false 时 action 必须是可用工具之一。"
            "当用户说“工作日提醒/每天提醒/仅明天”等对已有提醒的修改时，优先用 update_latest_reminder_recurrence。"
            "当用户查询“工作日有哪些提醒”时，优先用 list_workday_reminders。"
            "当用户说“提前N分钟提醒”时，在 create_reminder 的 action_input 里带 advance_minutes。"
            "当用户说“没回应继续提醒”时，设置 retry_interval_minutes 与 max_retries。"
            "当用户说“跳过明天/跳过这次提醒”时，优先用 skip_next_reminder。"
            "当用户说“暂停到某个时间再提醒”时，优先用 pause_latest_reminder_until。"
            "不要输出 markdown，不要输出额外文本。"
        )
        user = (
            f"provider={provider}\n"
            f"user_input={user_text}\n"
            f"last_reminder_id={state.get('last_reminder_id')}\n"
            f"last_reminder_content={state.get('last_reminder_content', '')}\n"
            f"available_tools={tools}\n"
            f"scratchpad={scratchpad}\n"
            "规则提示：\n"
            "- 用户说“每天/每日/天天”=> recurrence=DAILY\n"
            "- 用户说“工作日/周一到周五”=> recurrence=WEEKDAYS\n"
            "- 用户说“仅明天/只提醒一次”=> recurrence=NONE\n"
            "请决定下一步。"
        )
        return {"system": system, "user": user}

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except Exception:
            start = raw.find("{")
            end = raw.rfind("}")
            if start >= 0 and end > start:
                try:
                    return json.loads(raw[start : end + 1])
                except Exception:
                    return {}
            return {}

    @staticmethod
    def _agent_model() -> str:
        from app.config import settings

        return settings.intent_model.strip() or settings.llm_model

    def _available_actions(self) -> set[str]:
        return self._tool_registry.names() | {"answer"}

    def _build_tool_registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(
            AgentTool(
                name="create_reminder",
                description="Create a reminder from natural language time expression.",
                usage="create_reminder(text)",
                input_schema={"type": "object", "properties": {"text": {"type": "string"}}},
                handler=self._run_create_reminder,
            )
        )
        registry.register(
            AgentTool(
                name="update_latest_reminder_recurrence",
                description="Update latest reminder recurrence. recurrence must be NONE|DAILY|WEEKDAYS.",
                usage="update_latest_reminder_recurrence(recurrence|text)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "recurrence": {"type": "string", "enum": ["NONE", "DAILY", "WEEKDAYS"]},
                        "text": {"type": "string"},
                        "target_reminder_id": {"type": "integer"},
                    },
                },
                handler=self._run_update_latest_reminder_recurrence,
            )
        )
        registry.register(
            AgentTool(
                name="delay_latest_reminder",
                description="Delay latest reminder by minutes / hours / days.",
                usage="delay_latest_reminder(text|minutes|hours|days)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "minutes": {"type": "integer"},
                        "hours": {"type": "integer"},
                        "days": {"type": "integer"},
                        "target_reminder_id": {"type": "integer"},
                    },
                },
                handler=self._run_delay_latest_reminder,
            )
        )
        registry.register(
            AgentTool(
                name="skip_next_reminder",
                description="Skip next occurrence for latest reminder.",
                usage="skip_next_reminder(target_reminder_id?)",
                input_schema={
                    "type": "object",
                    "properties": {"target_reminder_id": {"type": "integer"}},
                },
                handler=self._run_skip_next_reminder,
            )
        )
        registry.register(
            AgentTool(
                name="pause_latest_reminder_until",
                description="Pause latest reminder until a datetime expression.",
                usage="pause_latest_reminder_until(text|until)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string"},
                        "until": {"type": "string"},
                        "target_reminder_id": {"type": "integer"},
                    },
                },
                handler=self._run_pause_latest_reminder_until,
            )
        )
        registry.register(
            AgentTool(
                name="check_reminders_status",
                description="Query sent and pending reminders for current user.",
                usage="check_reminders_status(limit=5)",
                input_schema={
                    "type": "object",
                    "properties": {"limit": {"type": "integer", "minimum": 1, "maximum": 20}},
                },
                handler=self._run_check_reminders_status,
            )
        )
        registry.register(
            AgentTool(
                name="list_workday_reminders",
                description="List reminders with WEEKDAYS recurrence.",
                usage="list_workday_reminders(limit=10, include_sent=false)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                        "include_sent": {"type": "boolean"},
                    },
                },
                handler=self._run_list_workday_reminders,
            )
        )
        registry.register(
            AgentTool(
                name="write_idea",
                description="Persist an idea note.",
                usage="write_idea(content)",
                input_schema={"type": "object", "properties": {"content": {"type": "string"}}},
                handler=self._run_write_idea,
            )
        )
        registry.register(
            AgentTool(
                name="write_task",
                description="Persist a task with priority.",
                usage="write_task(content, priority=LATER|NOW|DONE)",
                input_schema={
                    "type": "object",
                    "properties": {
                        "content": {"type": "string"},
                        "priority": {"type": "string", "enum": ["LATER", "NOW", "DONE"]},
                    },
                },
                handler=self._run_write_task,
            )
        )
        registry.register(
            AgentTool(
                name="write_note",
                description="Persist a plain note.",
                usage="write_note(content)",
                input_schema={"type": "object", "properties": {"content": {"type": "string"}}},
                handler=self._run_write_note,
            )
        )
        registry.register(
            AgentTool(
                name="search_memory",
                description="Retrieve top-k memory snippets from vector store.",
                usage="search_memory(query, top_k)",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}, "top_k": {"type": "integer"}},
                },
                handler=self._run_search_memory,
            )
        )
        registry.register(
            AgentTool(
                name="web_search",
                description="Search open web by keyword.",
                usage="web_search(query)",
                input_schema={"type": "object", "properties": {"query": {"type": "string"}}},
                handler=self._run_web_search,
            )
        )
        registry.register(
            AgentTool(
                name="write_logseq_doc",
                description="Write a composed document to Logseq.",
                usage="write_logseq_doc(title, content, links[])",
                input_schema={
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "links": {"type": "array", "items": {"type": "string"}},
                    },
                },
                handler=self._run_write_logseq_doc,
            )
        )
        return registry

    async def _run_create_reminder(self, ctx: ToolContext, payload: dict[str, Any]) -> ToolResult:
        return ToolResult(
            status="ok", observation=await self._tool_create_reminder(ctx.state, payload)
        )

    async def _run_update_latest_reminder_recurrence(
        self, ctx: ToolContext, payload: dict[str, Any]
    ) -> ToolResult:
        return ToolResult(
            status="ok",
            observation=await self._tool_update_latest_reminder_recurrence(ctx.state, payload),
        )

    async def _run_delay_latest_reminder(
        self, ctx: ToolContext, payload: dict[str, Any]
    ) -> ToolResult:
        return ToolResult(
            status="ok", observation=await self._tool_delay_latest_reminder(ctx.state, payload)
        )

    async def _run_skip_next_reminder(
        self, ctx: ToolContext, payload: dict[str, Any]
    ) -> ToolResult:
        return ToolResult(
            status="ok", observation=await self._tool_skip_next_reminder(ctx.state, payload)
        )

    async def _run_pause_latest_reminder_until(
        self, ctx: ToolContext, payload: dict[str, Any]
    ) -> ToolResult:
        return ToolResult(
            status="ok",
            observation=await self._tool_pause_latest_reminder_until(ctx.state, payload),
        )

    async def _run_check_reminders_status(
        self, ctx: ToolContext, payload: dict[str, Any]
    ) -> ToolResult:
        return ToolResult(
            status="ok", observation=await self._tool_check_reminders_status(ctx.state, payload)
        )

    async def _run_list_workday_reminders(
        self, ctx: ToolContext, payload: dict[str, Any]
    ) -> ToolResult:
        return ToolResult(
            status="ok",
            observation=await self._tool_list_workday_reminders(ctx.state, payload),
        )

    async def _run_write_idea(self, ctx: ToolContext, payload: dict[str, Any]) -> ToolResult:
        return ToolResult(status="ok", observation=await self._tool_write_idea(ctx.state, payload))

    async def _run_write_task(self, ctx: ToolContext, payload: dict[str, Any]) -> ToolResult:
        return ToolResult(status="ok", observation=await self._tool_write_task(ctx.state, payload))

    async def _run_write_note(self, ctx: ToolContext, payload: dict[str, Any]) -> ToolResult:
        return ToolResult(status="ok", observation=await self._tool_write_note(ctx.state, payload))

    async def _run_search_memory(self, ctx: ToolContext, payload: dict[str, Any]) -> ToolResult:
        return ToolResult(
            status="ok", observation=await self._tool_search_memory(ctx.state, payload)
        )

    async def _run_web_search(self, ctx: ToolContext, payload: dict[str, Any]) -> ToolResult:
        return ToolResult(status="ok", observation=await self._tool_web_search(ctx.state, payload))

    async def _run_write_logseq_doc(self, ctx: ToolContext, payload: dict[str, Any]) -> ToolResult:
        return ToolResult(
            status="ok", observation=await self._tool_write_logseq_doc(ctx.state, payload)
        )

    @staticmethod
    def _fallback_action_from_text(text: str) -> dict[str, Any] | None:
        cleaned = text.strip()
        if cleaned:
            return {
                "action": "write_note",
                "action_input": {"content": cleaned},
                "thought": "规划输出不可用，降级为普通记录。",
            }
        return None

    @staticmethod
    def _format_terminal_response(action: ActionName | None, observation: str) -> str:
        if action == "create_reminder" and observation.startswith("reminder_created:"):
            payload = observation.removeprefix("reminder_created:")
            return f"已为你创建提醒：{payload}"
        if action == "update_latest_reminder_recurrence" and observation.startswith(
            "reminder_recurrence_updated:"
        ):
            payload = observation.removeprefix("reminder_recurrence_updated:")
            return f"已更新提醒规则：{payload}"
        if action == "delay_latest_reminder" and observation.startswith("reminder_delayed:"):
            payload = observation.removeprefix("reminder_delayed:")
            return f"已为你顺延提醒：{payload}"
        if action == "skip_next_reminder" and observation.startswith("reminder_skipped:"):
            payload = observation.removeprefix("reminder_skipped:")
            return f"已跳过下一次提醒：{payload}"
        if action == "pause_latest_reminder_until" and observation.startswith("reminder_paused:"):
            payload = observation.removeprefix("reminder_paused:")
            return f"已暂停提醒：{payload}"
        if action == "check_reminders_status" and observation.startswith("reminder_status:"):
            return observation.removeprefix("reminder_status:")
        if action == "list_workday_reminders" and observation.startswith("workday_reminders:"):
            return observation.removeprefix("workday_reminders:")
        if action == "delay_latest_reminder" and observation == "reminder_delay_no_recent":
            return "没找到可顺延的最近提醒，请直接告诉我要提醒的内容和时间。"
        if action == "delay_latest_reminder" and observation == "delay_minutes_missing":
            return "我没识别到要延迟多少分钟，请说“延迟15分钟提醒我…”。"
        if action == "skip_next_reminder" and observation == "reminder_skip_no_recent":
            return "没找到可跳过的最近提醒。"
        if action == "pause_latest_reminder_until" and observation == "pause_until_missing":
            return "我没识别到要暂停到什么时候，请补充具体时间。"
        if action == "pause_latest_reminder_until" and observation == "reminder_pause_no_recent":
            return "没找到可暂停的最近提醒。"
        if action == "update_latest_reminder_recurrence" and observation == "recurrence_missing":
            return "我没识别到你想改成哪种规则，请说“每天提醒”或“工作日提醒”或“只明天提醒一次”。"
        if (
            action == "update_latest_reminder_recurrence"
            and observation == "recurrence_update_no_recent"
        ):
            return "没找到可修改的最近提醒，请先创建一个提醒。"
        if action == "write_idea":
            return "灵感已记录。"
        if action == "write_task":
            return "任务已记录。"
        if action == "write_note":
            return "已记录。"
        if action == "write_logseq_doc":
            return "文档已生成并写入 Logseq 日志。"
        return "处理完成。"

    async def _append_trace(self, data: dict[str, Any]) -> None:
        if not settings.agent_trace_enabled:
            return

        data = {
            "ts": datetime.now(UTC).isoformat(),
            **data,
        }
        logger.info(
            f"[agent-trace] run_id={data.get('run_id', '')} type={data.get('type', '')} "
            f"action={data.get('action', '')} obs={str(data.get('observation', ''))[:80]}"
        )

        trace_dir = settings.storage_path / "agent_traces"
        trace_dir.mkdir(parents=True, exist_ok=True)
        trace_file = trace_dir / f"{datetime.now(UTC).strftime('%Y-%m-%d')}.jsonl"
        line = json.dumps(data, ensure_ascii=False)
        await self._append_line(trace_file, line)

    @staticmethod
    async def _append_line(path: Path, line: str) -> None:
        def _write() -> None:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line + "\n")

        import asyncio

        await asyncio.to_thread(_write)

    async def _tool_create_reminder(self, state: AgentState, payload: dict[str, Any]) -> str:
        text = str(payload.get("text", "")).strip() or state.get("text", "")
        remind_at, content = ReminderService.parse_time_expression(text)
        if not remind_at:
            return "parse_reminder_failed"
        recurrence = str(payload.get("recurrence", "")).strip().upper() or None
        if recurrence not in {"NONE", "DAILY", "WEEKDAYS"}:
            recurrence = ReminderService.parse_recurrence_rule(text)
        advance_raw = payload.get("advance_minutes", 1)
        retry_interval_raw = payload.get("retry_interval_minutes", 0)
        max_retries_raw = payload.get("max_retries", 0)
        require_ack = bool(payload.get("require_ack", False))
        try:
            advance_minutes = max(0, int(advance_raw))
        except (TypeError, ValueError):
            advance_minutes = 1
        try:
            retry_interval_minutes = max(0, int(retry_interval_raw))
        except (TypeError, ValueError):
            retry_interval_minutes = 0
        try:
            max_retries = max(0, int(max_retries_raw))
        except (TypeError, ValueError):
            max_retries = 0
        content = content or "提醒!"
        reminder = await ReminderService.create_reminder(
            content=content,
            remind_at=remind_at,
            user_id=state.get("user_id", "default"),
            channel_id=state.get("channel_id"),
            provider=state.get("provider", "discord"),
            recurrence_rule=recurrence,
            advance_minutes=advance_minutes,
            retry_interval_minutes=retry_interval_minutes,
            max_retries=max_retries,
            require_ack=require_ack,
        )
        state["last_reminder_id"] = reminder.id
        state["last_reminder_content"] = reminder.content
        await self.note_service.write_reminder(
            content, remind_at, tags=[state.get("provider", "unknown")]
        )
        recurrence_desc = recurrence or "ONCE"
        return f"reminder_created:#{reminder.id} {reminder.content}@{remind_at.isoformat()}[{recurrence_desc}]"

    async def _tool_update_latest_reminder_recurrence(
        self, state: AgentState, payload: dict[str, Any]
    ) -> str:
        recurrence = str(payload.get("recurrence", "")).strip().upper()
        if recurrence not in {"NONE", "DAILY", "WEEKDAYS"}:
            text = str(payload.get("text", "")).strip() or state.get("text", "")
            parsed = ReminderService.parse_recurrence_rule(text)
            recurrence = parsed or ""
        if recurrence not in {"NONE", "DAILY", "WEEKDAYS"}:
            return "recurrence_missing"

        target_id_raw = payload.get("target_reminder_id")
        target_id: int | None = None
        if isinstance(target_id_raw, int) and target_id_raw > 0:
            target_id = target_id_raw
        elif isinstance(state.get("last_reminder_id"), int):
            target_id = state.get("last_reminder_id")

        reminder = await ReminderService.update_latest_reminder_recurrence(
            user_id=state.get("user_id", "default"),
            recurrence_rule=recurrence,
            provider=state.get("provider", "discord"),
            channel_id=state.get("channel_id"),
            target_reminder_id=target_id,
        )
        if reminder is None:
            return "recurrence_update_no_recent"
        state["last_reminder_id"] = reminder.id
        state["last_reminder_content"] = reminder.content
        rule = reminder.recurrence_rule or "ONCE"
        return (
            f"reminder_recurrence_updated:#{reminder.id} "
            f"{reminder.content}@{reminder.remind_at.isoformat()}[{rule}]"
        )

    async def _tool_delay_latest_reminder(self, state: AgentState, payload: dict[str, Any]) -> str:
        minutes_raw = payload.get("minutes")
        hours_raw = payload.get("hours")
        days_raw = payload.get("days")
        text = str(payload.get("text", "")).strip() or state.get("text", "")

        delta = None
        if isinstance(minutes_raw, int) and minutes_raw > 0:
            from datetime import timedelta

            delta = timedelta(minutes=minutes_raw)
        elif isinstance(hours_raw, int) and hours_raw > 0:
            from datetime import timedelta

            delta = timedelta(hours=hours_raw)
        elif isinstance(days_raw, int) and days_raw > 0:
            from datetime import timedelta

            delta = timedelta(days=days_raw)
        else:
            delta = ReminderService.parse_snooze_delta(text)
            if delta is None:
                delay_minutes = ReminderService.parse_delay_minutes(text)
                if delay_minutes:
                    from datetime import timedelta

                    delta = timedelta(minutes=delay_minutes)

        if delta is None or delta.total_seconds() <= 0:
            return "delay_minutes_missing"

        target_id = (
            state.get("last_reminder_id")
            if isinstance(state.get("last_reminder_id"), int)
            else None
        )
        reminder = await ReminderService.snooze_latest_reminder(
            user_id=state.get("user_id", "default"),
            delta=delta,
            provider=state.get("provider", "discord"),
            channel_id=state.get("channel_id"),
            target_reminder_id=target_id,
        )
        if reminder is None:
            return "reminder_delay_no_recent"
        state["last_reminder_id"] = reminder.id
        state["last_reminder_content"] = reminder.content

        delay_minutes = int(delta.total_seconds() // 60)
        await self.note_service.write_note(
            f"提醒顺延 {delay_minutes} 分钟：{reminder.content} @ {reminder.remind_at.isoformat()}",
            tags=[state.get("provider", "unknown"), "reminder"],
        )
        return f"reminder_delayed:{reminder.content}@{reminder.remind_at.isoformat()}"

    async def _tool_skip_next_reminder(self, state: AgentState, payload: dict[str, Any]) -> str:
        target_raw = payload.get("target_reminder_id")
        target_id = target_raw if isinstance(target_raw, int) else state.get("last_reminder_id")
        reminder = await ReminderService.skip_next_occurrence(
            user_id=state.get("user_id", "default"),
            provider=state.get("provider", "discord"),
            channel_id=state.get("channel_id"),
            target_reminder_id=target_id if isinstance(target_id, int) else None,
        )
        if reminder is None:
            return "reminder_skip_no_recent"
        state["last_reminder_id"] = reminder.id
        state["last_reminder_content"] = reminder.content
        return (
            f"reminder_skipped:#{reminder.id} {reminder.content}@{reminder.remind_at.isoformat()}"
        )

    async def _tool_pause_latest_reminder_until(
        self, state: AgentState, payload: dict[str, Any]
    ) -> str:
        until_text = str(payload.get("until", "")).strip()
        if not until_text:
            until_text = str(payload.get("text", "")).strip() or state.get("text", "")
        pause_until, _ = ReminderService.parse_time_expression(until_text)
        if pause_until is None:
            return "pause_until_missing"
        target_raw = payload.get("target_reminder_id")
        target_id = target_raw if isinstance(target_raw, int) else state.get("last_reminder_id")
        reminder = await ReminderService.pause_latest_reminder_until(
            user_id=state.get("user_id", "default"),
            pause_until=pause_until,
            provider=state.get("provider", "discord"),
            channel_id=state.get("channel_id"),
            target_reminder_id=target_id if isinstance(target_id, int) else None,
        )
        if reminder is None:
            return "reminder_pause_no_recent"
        state["last_reminder_id"] = reminder.id
        state["last_reminder_content"] = reminder.content
        return f"reminder_paused:#{reminder.id} {reminder.content} until {pause_until.isoformat()}"

    async def _tool_check_reminders_status(self, state: AgentState, payload: dict[str, Any]) -> str:
        limit_raw = payload.get("limit", 8)
        try:
            limit = max(1, min(int(limit_raw), 20))
        except (TypeError, ValueError):
            limit = 8

        sent, pending = await ReminderService.get_reminder_status(
            user_id=state.get("user_id", "default"),
            provider=state.get("provider", "discord"),
            channel_id=state.get("channel_id"),
            limit=limit,
        )

        lines: list[str] = []
        if sent:
            lines.append("已提醒：")
            for i, item in enumerate(sent, 1):
                sent_at = item.sent_at.strftime("%Y-%m-%d %H:%M") if item.sent_at else "未知时间"
                rule = item.recurrence_rule or "ONCE"
                lines.append(f"{i}. {item.content}（已提醒于 {sent_at}，规则 {rule}）")
        else:
            lines.append("已提醒：暂无")

        if pending:
            lines.append("未提醒：")
            for i, item in enumerate(pending, 1):
                remind_at = item.remind_at.strftime("%Y-%m-%d %H:%M")
                rule = item.recurrence_rule or "ONCE"
                lines.append(f"{i}. {item.content}（计划 {remind_at}，规则 {rule}）")
        else:
            lines.append("未提醒：暂无")

        return f"reminder_status:{'\n'.join(lines)}"

    async def _tool_list_workday_reminders(self, state: AgentState, payload: dict[str, Any]) -> str:
        limit_raw = payload.get("limit", 10)
        include_sent_raw = payload.get("include_sent", False)
        try:
            limit = max(1, min(int(limit_raw), 20))
        except (TypeError, ValueError):
            limit = 10
        include_sent = bool(include_sent_raw)

        sent, pending = await ReminderService.get_workday_reminders(
            user_id=state.get("user_id", "default"),
            provider=state.get("provider", "discord"),
            channel_id=state.get("channel_id"),
            include_sent=include_sent,
            limit=limit,
        )

        lines: list[str] = ["工作日提醒："]
        if pending:
            lines.append("未提醒：")
            for i, item in enumerate(pending, 1):
                lines.append(f"{i}. {item.content}（{item.remind_at.strftime('%Y-%m-%d %H:%M')}）")
        else:
            lines.append("未提醒：暂无")

        if include_sent:
            if sent:
                lines.append("已提醒：")
                for i, item in enumerate(sent, 1):
                    sent_at = (
                        item.sent_at.strftime("%Y-%m-%d %H:%M") if item.sent_at else "未知时间"
                    )
                    lines.append(f"{i}. {item.content}（{sent_at}）")
            else:
                lines.append("已提醒：暂无")

        return f"workday_reminders:{'\n'.join(lines)}"

    async def _tool_write_idea(self, state: AgentState, payload: dict[str, Any]) -> str:
        content = str(payload.get("content", "")).strip() or state.get("text", "")
        await self.note_service.write_idea(content, tags=[state.get("provider", "unknown")])
        return "idea_written"

    async def _tool_write_task(self, state: AgentState, payload: dict[str, Any]) -> str:
        content = str(payload.get("content", "")).strip() or state.get("text", "")
        priority_raw = str(payload.get("priority", "LATER")).strip().upper()
        priority = {
            "NOW": TaskPriority.NOW,
            "DONE": TaskPriority.DONE,
            "LATER": TaskPriority.LATER,
        }.get(priority_raw, TaskPriority.LATER)
        await self.note_service.write_task(
            content, priority=priority, tags=[state.get("provider", "unknown")]
        )
        return f"task_written:{priority.value}"

    async def _tool_write_note(self, state: AgentState, payload: dict[str, Any]) -> str:
        content = str(payload.get("content", "")).strip() or state.get("text", "")
        await self.note_service.write_note(content, tags=[state.get("provider", "unknown")])
        return "note_written"

    async def _tool_search_memory(self, state: AgentState, payload: dict[str, Any]) -> str:
        query = str(payload.get("query", "")).strip()
        top_k = int(payload.get("top_k", 5))
        if not query:
            return "memory_search_empty_query"

        embedding = await self.llm_service.get_embedding(query)
        results = self.vector_store.search(embedding, top_k=top_k)
        if not results:
            return "memory_search_no_result"

        lines = []
        for row in results[:top_k]:
            item_id = int(row["item_id"])
            item = await self.knowledge_repo.get_by_id(item_id)
            if not item:
                continue
            text = (item.structured_text or item.raw_text or "")[:180]
            lines.append(f"[knowledge_id={item.id};distance={row['distance']:.4f}] {text}")
        return "\n".join(lines) if lines else "memory_search_no_resolved_item"

    async def _tool_web_search(self, state: AgentState, payload: dict[str, Any]) -> str:
        query = str(payload.get("query", "")).strip()
        if not query:
            return "web_search_empty_query"

        url = "https://zh.wikipedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": query,
            "utf8": 1,
            "format": "json",
            "srlimit": 3,
        }
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
                data = resp.json()
            rows = data.get("query", {}).get("search", [])
            if not rows:
                return "web_search_no_result"
            lines = []
            for row in rows:
                title = row.get("title", "")
                snippet = (
                    str(row.get("snippet", ""))
                    .replace('<span class="searchmatch">', "")
                    .replace("</span>", "")
                )
                lines.append(f"[web]{title}: {snippet}")
            return "\n".join(lines)
        except Exception as e:
            return f"web_search_error:{e}"

    async def _tool_write_logseq_doc(self, state: AgentState, payload: dict[str, Any]) -> str:
        title = str(payload.get("title", "")).strip()
        content = str(payload.get("content", "")).strip()
        links = payload.get("links", []) or []
        if not title:
            return "write_doc_missing_title"
        link_text = " ".join([f"[[{str(link).strip()}]]" for link in links if str(link).strip()])
        full = f"# {title}\n\n{content}\n\n{link_text}".strip()
        await self.note_service.write_note(full, tags=["doc"])
        return "logseq_doc_written"
