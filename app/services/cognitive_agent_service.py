import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, TypedDict
from uuid import uuid4

import httpx
from langgraph.graph import END, StateGraph

from app.config import settings
from app.note import NoteService, TaskPriority
from app.repositories import KnowledgeItemRepository
from app.services.llm_service import LLMService
from app.services.reminder_service import ReminderService
from app.services.vector_store import VectorStore
from app.utils import logger

ActionName = Literal[
    "create_reminder",
    "delay_latest_reminder",
    "check_reminders_status",
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
        self._graph = self._build_graph()

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
                "done": False,
            }
        )
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

        fast_path = self._heuristic_plan(state.get("text", ""))
        if fast_path is not None:
            return {
                **state,
                "action": fast_path["action"],
                "action_input": fast_path["action_input"],
                "thought": fast_path["thought"],
                "steps": steps + 1,
            }

        scratchpad = state.get("scratchpad", [])
        prompt = self._planner_prompt(
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

        if action not in {
            "create_reminder",
            "delay_latest_reminder",
            "check_reminders_status",
            "write_idea",
            "write_task",
            "write_note",
            "search_memory",
            "web_search",
            "write_logseq_doc",
            "answer",
        }:
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
            if action == "create_reminder":
                observation = await self._tool_create_reminder(state, payload)
            elif action == "delay_latest_reminder":
                observation = await self._tool_delay_latest_reminder(state, payload)
            elif action == "check_reminders_status":
                observation = await self._tool_check_reminders_status(state, payload)
            elif action == "write_idea":
                observation = await self._tool_write_idea(state, payload)
            elif action == "write_task":
                observation = await self._tool_write_task(state, payload)
            elif action == "write_note":
                observation = await self._tool_write_note(state, payload)
            elif action == "search_memory":
                observation = await self._tool_search_memory(payload)
            elif action == "web_search":
                observation = await self._tool_web_search(payload)
            elif action == "write_logseq_doc":
                observation = await self._tool_write_logseq_doc(payload)
            elif action == "answer":
                return {
                    **state,
                    "done": True,
                    "response": str(payload.get("text", "")).strip() or "处理完成。",
                }
            else:
                observation = "unknown_action"
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
            "reminder_delayed:",
            "reminder_status:",
            "idea_written",
            "task_written:",
            "note_written",
            "logseq_doc_written",
        )
        terminal_error_prefix = (
            "parse_reminder_failed",
            "delay_minutes_missing",
            "reminder_delay_no_recent",
            "tool_error:",
            "unknown_action",
            "write_doc_missing_title",
        )
        terminal_error_immediate = {
            "delay_minutes_missing",
            "reminder_delay_no_recent",
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
        self, user_text: str, provider: str, scratchpad: list[str]
    ) -> dict[str, str]:
        tools = [
            "create_reminder(text)",
            "delay_latest_reminder(text|minutes)",
            "check_reminders_status(limit=5)",
            "write_idea(content)",
            "write_task(content, priority=LATER|NOW|DONE)",
            "write_note(content)",
            "search_memory(query, top_k)",
            "web_search(query)",
            "write_logseq_doc(title, content, links[])",
            "answer(text)",
        ]
        system = (
            "你是 CognitiveOS 的认知代理。目标是通过多步工具调用完成用户任务。"
            "每一步必须输出严格 JSON: "
            '{"done":bool,"thought":str,"action":str,"action_input":{},"response":str}。'
            "done=true 时可直接返回最终 response。"
            "done=false 时 action 必须是可用工具之一。"
            "不要输出 markdown，不要输出额外文本。"
        )
        user = (
            f"provider={provider}\n"
            f"user_input={user_text}\n"
            f"available_tools={tools}\n"
            f"scratchpad={scratchpad}\n"
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

    @staticmethod
    def _heuristic_plan(text: str) -> dict[str, Any] | None:
        cleaned = text.strip()

        if cleaned.startswith("任务"):
            content = cleaned.removeprefix("任务").strip(" ：:，,")
            return {
                "action": "write_task",
                "action_input": {"content": content or cleaned, "priority": "LATER"},
                "thought": "检测到任务前缀，直接记录任务。",
            }

        if cleaned.startswith("灵感"):
            content = cleaned.removeprefix("灵感").strip(" ：:，,")
            return {
                "action": "write_idea",
                "action_input": {"content": content or cleaned},
                "thought": "检测到灵感前缀，直接记录灵感。",
            }

        delay_minutes = ReminderService.parse_delay_minutes(text)
        if delay_minutes is not None:
            return {
                "action": "delay_latest_reminder",
                "action_input": {"minutes": delay_minutes, "text": text},
                "thought": "检测到延迟提醒意图，直接顺延最近提醒。",
            }
        check_keywords = ("已经提醒", "哪些提醒", "提醒事项", "没提醒", "还有没有", "提醒了吗")
        if "提醒" in text and any(keyword in text for keyword in check_keywords):
            return {
                "action": "check_reminders_status",
                "action_input": {"limit": 8},
                "thought": "检测到提醒状态查询意图，直接查询提醒状态。",
            }
        return None

    @staticmethod
    def _fallback_action_from_text(text: str) -> dict[str, Any] | None:
        heuristic = CognitiveAgentService._heuristic_plan(text)
        if heuristic is not None:
            return heuristic
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
        if action == "delay_latest_reminder" and observation.startswith("reminder_delayed:"):
            payload = observation.removeprefix("reminder_delayed:")
            return f"已为你顺延提醒：{payload}"
        if action == "check_reminders_status" and observation.startswith("reminder_status:"):
            return observation.removeprefix("reminder_status:")
        if action == "delay_latest_reminder" and observation == "reminder_delay_no_recent":
            return "没找到可顺延的最近提醒，请直接告诉我要提醒的内容和时间。"
        if action == "delay_latest_reminder" and observation == "delay_minutes_missing":
            return "我没识别到要延迟多少分钟，请说“延迟15分钟提醒我…”。"
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
        content = content or "提醒!"
        await ReminderService.create_reminder(
            content=content,
            remind_at=remind_at,
            user_id=state.get("user_id", "default"),
            channel_id=state.get("channel_id"),
            provider=state.get("provider", "discord"),
        )
        await self.note_service.write_reminder(
            content, remind_at, tags=[state.get("provider", "unknown")]
        )
        return f"reminder_created:{content}@{remind_at.isoformat()}"

    async def _tool_delay_latest_reminder(self, state: AgentState, payload: dict[str, Any]) -> str:
        minutes_raw = payload.get("minutes")
        delay_minutes: int | None
        if isinstance(minutes_raw, int):
            delay_minutes = minutes_raw
        else:
            text = str(payload.get("text", "")).strip() or state.get("text", "")
            delay_minutes = ReminderService.parse_delay_minutes(text)

        if delay_minutes is None or delay_minutes <= 0:
            return "delay_minutes_missing"

        reminder = await ReminderService.delay_latest_reminder(
            user_id=state.get("user_id", "default"),
            delay_minutes=delay_minutes,
            provider=state.get("provider", "discord"),
            channel_id=state.get("channel_id"),
        )
        if reminder is None:
            return "reminder_delay_no_recent"

        await self.note_service.write_note(
            f"提醒顺延 {delay_minutes} 分钟：{reminder.content} @ {reminder.remind_at.isoformat()}",
            tags=[state.get("provider", "unknown"), "reminder"],
        )
        return f"reminder_delayed:{reminder.content}@{reminder.remind_at.isoformat()}"

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
                lines.append(f"{i}. {item.content}（已提醒于 {sent_at}）")
        else:
            lines.append("已提醒：暂无")

        if pending:
            lines.append("未提醒：")
            for i, item in enumerate(pending, 1):
                remind_at = item.remind_at.strftime("%Y-%m-%d %H:%M")
                lines.append(f"{i}. {item.content}（计划 {remind_at}）")
        else:
            lines.append("未提醒：暂无")

        return f"reminder_status:{'\n'.join(lines)}"

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

    async def _tool_search_memory(self, payload: dict[str, Any]) -> str:
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

    @staticmethod
    async def _tool_web_search(payload: dict[str, Any]) -> str:
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

    async def _tool_write_logseq_doc(self, payload: dict[str, Any]) -> str:
        title = str(payload.get("title", "")).strip()
        content = str(payload.get("content", "")).strip()
        links = payload.get("links", []) or []
        if not title:
            return "write_doc_missing_title"
        link_text = " ".join([f"[[{str(link).strip()}]]" for link in links if str(link).strip()])
        full = f"# {title}\n\n{content}\n\n{link_text}".strip()
        await self.note_service.write_note(full, tags=["doc"])
        return "logseq_doc_written"
