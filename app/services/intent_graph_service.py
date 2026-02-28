import json
import re
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from app.config import settings
from app.services.llm_service import LLMService
from app.utils import logger

try:
    from langgraph.graph import END, StateGraph

    LANGGRAPH_AVAILABLE = True
except ModuleNotFoundError:  # pragma: no cover - optional dependency
    LANGGRAPH_AVAILABLE = False
    END = None
    StateGraph = None

IntentName = Literal["idea", "task", "reminder", "note", "help", "ping", "list_reminders", "ignore"]
TaskPriorityName = Literal["LATER", "NOW", "DONE"]


@dataclass
class IntentResult:
    intent: IntentName
    content: str
    confidence: float
    task_priority: TaskPriorityName = "LATER"
    reason: str = ""


class IntentState(TypedDict, total=False):
    text: str
    intent: IntentName
    content: str
    confidence: float
    task_priority: TaskPriorityName
    reason: str


class IntentGraphService:
    ALLOWED_INTENTS: set[str] = {
        "idea",
        "task",
        "reminder",
        "note",
        "help",
        "ping",
        "list_reminders",
        "ignore",
    }
    ALLOWED_PRIORITIES: set[str] = {"LATER", "NOW", "DONE"}

    def __init__(self, llm_service: LLMService | None = None) -> None:
        self._llm_service = llm_service or LLMService()
        self._model = (
            settings.intent_model.strip() if settings.intent_model.strip() else settings.llm_model
        )
        self._enabled = settings.intent_enabled
        self._threshold = settings.intent_confidence_threshold
        self._graph = self._build_graph() if (self._enabled and LANGGRAPH_AVAILABLE) else None

        if self._enabled and not LANGGRAPH_AVAILABLE:
            logger.warning(
                "LangGraph is not installed, intent routing falls back to heuristic mode"
            )

    def _build_graph(self):
        assert StateGraph is not None and END is not None
        builder = StateGraph(IntentState)
        builder.add_node("classify", self._classify_node)
        builder.set_entry_point("classify")
        builder.add_edge("classify", END)
        return builder.compile()

    async def classify(self, text: str) -> IntentResult:
        cleaned = text.strip()
        if not cleaned:
            return IntentResult(intent="ignore", content="", confidence=1.0, reason="empty")

        if not self._enabled:
            return self._heuristic(cleaned)

        if self._graph is None:
            return self._heuristic(cleaned)

        try:
            state: IntentState = await self._graph.ainvoke({"text": cleaned})
            intent = state.get("intent", "note")
            content = state.get("content", cleaned).strip()
            confidence = float(state.get("confidence", 0.0))
            task_priority = state.get("task_priority", "LATER")
            reason = state.get("reason", "")

            if confidence < self._threshold:
                return self._heuristic(cleaned, reason=f"low_confidence:{confidence:.2f}")

            return IntentResult(
                intent=intent,
                content=content if content else cleaned,
                confidence=confidence,
                task_priority=task_priority,
                reason=reason,
            )
        except Exception as e:
            logger.warning(f"Intent graph failed, fallback to heuristic: {e}")
            return self._heuristic(cleaned, reason="graph_exception")

    async def _classify_node(self, state: IntentState) -> IntentState:
        text = state.get("text", "").strip()
        if not text:
            return {
                "intent": "ignore",
                "content": "",
                "confidence": 1.0,
                "task_priority": "LATER",
                "reason": "empty",
            }

        result = await self._llm_classify(text)
        return {
            "intent": result.intent,
            "content": result.content,
            "confidence": result.confidence,
            "task_priority": result.task_priority,
            "reason": result.reason,
        }

    async def _llm_classify(self, text: str) -> IntentResult:
        system_prompt = (
            "You are an intent classifier for a personal assistant. "
            "Classify user text into one intent in: "
            "idea, task, reminder, note, help, ping, list_reminders, ignore. "
            "Return strict JSON only with keys: intent, content, confidence, task_priority, reason. "
            "task_priority must be one of LATER/NOW/DONE. "
            "confidence is float [0,1]. "
            "For reminder intent, keep the original natural-language time expression in content."
        )
        user_prompt = f"Text:\n{text}\n\nJSON:"

        raw = await self._llm_service.chat_with_system(
            system_prompt=system_prompt,
            user_message=user_prompt,
            temperature=0.0,
            max_tokens=settings.intent_max_tokens,
            model=self._model,
            base_url=settings.intent_base_url or None,
            api_key=settings.intent_api_key or None,
        )
        data = self._extract_json(raw)

        intent_raw = str(data.get("intent", "note")).strip().lower()
        intent: IntentName = intent_raw if intent_raw in self.ALLOWED_INTENTS else "note"

        content = str(data.get("content", text)).strip() or text
        confidence = float(data.get("confidence", 0.0))
        confidence = max(0.0, min(1.0, confidence))

        prio_raw = str(data.get("task_priority", "LATER")).strip().upper()
        task_priority: TaskPriorityName = (
            prio_raw if prio_raw in self.ALLOWED_PRIORITIES else "LATER"
        )
        reason = str(data.get("reason", "")).strip()

        return IntentResult(
            intent=intent,
            content=content,
            confidence=confidence,
            task_priority=task_priority,
            reason=reason,
        )

    @staticmethod
    def _extract_json(raw: str) -> dict[str, Any]:
        try:
            return json.loads(raw)
        except Exception:
            pass

        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                pass
        return {}

    def _heuristic(self, text: str, reason: str = "heuristic") -> IntentResult:
        lower = text.lower()

        if lower in ("help", "帮助"):
            return IntentResult("help", text, 0.8, reason=reason)
        if lower in ("ping",):
            return IntentResult("ping", text, 0.8, reason=reason)
        if lower in ("提醒列表", "list reminders"):
            return IntentResult("list_reminders", text, 0.8, reason=reason)

        if any(token in text for token in ("分钟后", "小时后", "天后", "明天", "下班前", "今天")):
            return IntentResult("reminder", text, 0.7, reason=reason)

        if text.startswith(("灵感", "idea ")):
            return IntentResult("idea", text, 0.8, reason=reason)

        if text.startswith(("任务", "task", "todo")):
            priority: TaskPriorityName = "LATER"
            if text.startswith(("紧急", "now", "重要")):
                priority = "NOW"
            if text.startswith(("完成", "done")):
                priority = "DONE"
            return IntentResult("task", text, 0.75, task_priority=priority, reason=reason)

        return IntentResult("note", text, 0.6, reason=reason)
