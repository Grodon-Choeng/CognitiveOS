import pytest

from app.application.audit.dto import AuditEventDTO, AuditEventPageDTO
from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.dto import ConversationInboundResult
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.results import AssistantExecutionResult
from app.application.conversations.kernel.state import AssistantTurnContext
from app.application.conversations.ports import (
    ConversationContextResolver,
    ResolvedConversationContext,
)
from app.application.conversations.service import (
    ConversationApplicationService,
    LLMConversationFallbackResponder,
)
from app.infrastructure.llm.models import GenerateRequest, GenerateResult
from app.infrastructure.types import JSONObject
from app.observability.message_events import MessageEventRecord


class FakeConversationContextResolver(ConversationContextResolver):
    async def resolve_for_outbound(
        self,
        *,
        provided_conversation_id: str | None,
        provided_session_id: str | None,
        source_channel: str | None,
        source_user_id: str | None,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext:
        _ = (
            provided_conversation_id,
            provided_session_id,
            source_channel,
            source_user_id,
            source_chat_id,
            source_thread_id,
        )
        return ResolvedConversationContext(
            conversation_id="conversation-test",
            session_id="session-test",
        )

    async def resolve_for_inbound(
        self,
        *,
        source_channel: str,
        source_user_id: str,
        source_chat_id: str | None,
        source_thread_id: str | None,
    ) -> ResolvedConversationContext:
        _ = (source_channel, source_user_id, source_chat_id, source_thread_id)
        return ResolvedConversationContext(
            conversation_id="conversation-test",
            session_id="session-test",
        )


class FakeMessageEventRecorder:
    def __init__(self) -> None:
        self.records: list[object] = []

    async def record(self, record: object) -> None:
        self.records.append(record)


class FakeHistoryReader:
    async def list_events(
        self,
        *,
        kind: str,
        conversation_id: str | None = None,
        session_id: str | None = None,
        success: bool | None = None,
        channel: str | None = None,
        provider: str | None = None,
        tool_name: str | None = None,
        workflow_type: str | None = None,
        recorded_after: object | None = None,
        recorded_before: object | None = None,
        cursor: str | None = None,
        limit: int = 50,
    ) -> AuditEventPageDTO:
        _ = (
            kind,
            conversation_id,
            session_id,
            success,
            channel,
            provider,
            tool_name,
            workflow_type,
            recorded_after,
            recorded_before,
            cursor,
            limit,
        )
        return AuditEventPageDTO(
            items=[
                AuditEventDTO(
                    kind="message",
                    event_id="evt-0",
                    recorded_at="2026-03-23T11:59:00+08:00",
                    conversation_id="conversation-test",
                    session_id="session-test",
                    trace_id=None,
                    chain_id=None,
                    request_id=None,
                    success=True,
                    summary="inbound:feishu:text",
                    payload={"direction": "inbound", "text": "hey"},
                ),
                AuditEventDTO(
                    kind="message",
                    event_id="evt-1",
                    recorded_at="2026-03-23T12:00:00+08:00",
                    conversation_id="conversation-test",
                    session_id="session-test",
                    trace_id=None,
                    chain_id=None,
                    request_id=None,
                    success=True,
                    summary="outbound:feishu:text",
                    payload={"direction": "outbound", "text": "你好，我可以帮你记提醒和待办。"},
                ),
            ]
        )


class FakeFallbackLLMGateway:
    def __init__(self, content: str) -> None:
        self.content = content
        self.last_request: GenerateRequest | None = None

    async def generate(self, request: GenerateRequest) -> GenerateResult:
        self.last_request = request
        return GenerateResult(
            content=self.content,
            model="gpt-test",
            provider="openai",
        )


class FakeReminderHandler:
    def __init__(
        self,
        result: ConversationInboundResult | None = None,
        *,
        raises: bool = False,
    ) -> None:
        self.result = result
        self.raises = raises

    async def handle(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        conversation_id: str,
        session_id: str,
    ) -> ConversationInboundResult | None:
        _ = (command, conversation_id, session_id)
        if self.raises:
            raise RuntimeError("处理失败")
        return self.result


class FakeTurnContextBuilder:
    async def build(
        self,
        *,
        conversation_id: str,
        session_id: str,
        latest_user_text: str | None,
    ) -> AssistantTurnContext:
        return AssistantTurnContext(
            conversation_id=conversation_id,
            session_id=session_id,
            latest_user_text=latest_user_text,
            metadata={
                "pending_tasks": [
                    {
                        "object_type": "task",
                        "object_id": "task-1",
                        "title": "整理纪要",
                        "status": "pending",
                    }
                ]
            },
        )


class FakePlanner:
    def __init__(self, plan: AssistantActionPlan | None = None, *, raises: bool = False) -> None:
        self.plan_result = plan or AssistantActionPlan(
            intent="task_list",
            action="list_tasks",
            object_type="task",
            object_id=None,
            confidence=0.9,
            reasoning="rules",
        )
        self.raises = raises

    async def plan(
        self,
        command: HandleInboundConversationMessageCommand,
        *,
        turn_context: AssistantTurnContext,
    ) -> AssistantActionPlan:
        _ = (command, turn_context)
        if self.raises:
            raise RuntimeError("规划失败")
        return self.plan_result


class FakeExecutor:
    def __init__(
        self,
        result: AssistantExecutionResult | None = None,
        *,
        raises: bool = False,
    ) -> None:
        self.result = result
        self.raises = raises

    async def execute(
        self,
        plan: AssistantActionPlan,
        *,
        command: HandleInboundConversationMessageCommand,
        turn_context: AssistantTurnContext,
    ) -> AssistantExecutionResult | None:
        _ = (plan, command, turn_context)
        if self.raises:
            raise RuntimeError("执行失败")
        return self.result


class FakeRenderer:
    def __init__(self, text: str = "好的，已处理。") -> None:
        self.text = text

    def render(self, result: object, *, turn_context: AssistantTurnContext) -> str:
        _ = (result, turn_context)
        return self.text


class FakeTurnStateStore:
    def __init__(self) -> None:
        self.saved: list[tuple[str, str, object]] = []

    async def load(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> JSONObject | None:
        _ = (conversation_id, session_id)
        return None

    async def save(
        self,
        *,
        conversation_id: str,
        session_id: str,
        state: JSONObject,
    ) -> None:
        self.saved.append((conversation_id, session_id, state))


def _build_service(
    *,
    recorder: FakeMessageEventRecorder,
    reminder_handler: FakeReminderHandler | None = None,
    planner: FakePlanner | None = None,
    executor: FakeExecutor | None = None,
    renderer: FakeRenderer | None = None,
    fallback_responder: LLMConversationFallbackResponder | None = None,
    turn_state_store: FakeTurnStateStore | None = None,
) -> ConversationApplicationService:
    return ConversationApplicationService(
        conversation_context_resolver=FakeConversationContextResolver(),
        message_event_recorder=recorder,
        reminder_handler=reminder_handler or FakeReminderHandler(),
        turn_context_builder=FakeTurnContextBuilder(),
        turn_state_store=turn_state_store or FakeTurnStateStore(),
        planner=planner or FakePlanner(),
        executor=executor
        or FakeExecutor(
            AssistantExecutionResult(
                success=True,
                action="list_tasks",
                object_type="task",
                payload={
                    "items": [
                        {
                            "object_type": "task",
                            "object_id": "task-1",
                            "title": "整理纪要",
                            "status": "pending",
                        }
                    ]
                },
            )
        ),
        renderer=renderer or FakeRenderer(),
        fallback_responder=fallback_responder,
    )


@pytest.mark.asyncio
async def test_conversation_service_uses_reminder_fast_path_first() -> None:
    recorder = FakeMessageEventRecorder()
    service = _build_service(
        recorder=recorder,
        reminder_handler=FakeReminderHandler(
            ConversationInboundResult(
                handled=True,
                conversation_id="conversation-test",
                session_id="session-test",
                handled_by="reminder",
                reason="reminder_replied",
                response_text="好的，已将这条提醒标记为完成。",
            )
        ),
    )

    result = await service.handle_inbound_message(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="收到",
            raw_payload={"text": "收到"},
        )
    )

    assert result.handled is True
    assert result.handled_by == "reminder"
    record = recorder.records[0]
    assert isinstance(record, MessageEventRecord)
    assert record.metadata["handled_by"] == "reminder"
    state = record.metadata["assistant_turn_state"]
    assert isinstance(state, dict)
    last_action = state["last_assistant_action"]
    assert isinstance(last_action, dict)
    assert last_action["action_type"] == "reply_reminder"


@pytest.mark.asyncio
async def test_conversation_service_runs_kernel_path_and_records_state() -> None:
    recorder = FakeMessageEventRecorder()
    turn_state_store = FakeTurnStateStore()
    service = _build_service(
        recorder=recorder,
        renderer=FakeRenderer("你现在还有 1 个待办。"),
        turn_state_store=turn_state_store,
    )

    result = await service.handle_inbound_message(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="查看待办",
            raw_payload={"text": "查看待办"},
        )
    )

    assert result.handled is True
    assert result.handled_by == "task"
    assert result.reason == "task_listed_via_rules"
    assert result.response_text == "你现在还有 1 个待办。"
    record = recorder.records[0]
    assert isinstance(record, MessageEventRecord)
    assert record.metadata["handled"] is True
    state = record.metadata["assistant_turn_state"]
    assert isinstance(state, dict)
    visible_candidates = state["visible_candidates"]
    assert isinstance(visible_candidates, list)
    first_candidate = visible_candidates[0]
    assert isinstance(first_candidate, dict)
    assert first_candidate["object_id"] == "task-1"
    assert turn_state_store.saved


@pytest.mark.asyncio
async def test_conversation_service_returns_default_guidance_when_kernel_cannot_handle() -> None:
    recorder = FakeMessageEventRecorder()
    service = _build_service(
        recorder=recorder,
        planner=FakePlanner(
            AssistantActionPlan(
                intent="unknown",
                action=None,
                object_type=None,
                object_id=None,
                status="unsupported",
            )
        ),
        executor=FakeExecutor(None),
    )

    result = await service.handle_inbound_message(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="？？？",
            raw_payload={"text": "？？？"},
        )
    )

    assert result.handled is False
    assert result.reason == "no_handler_accepted"
    assert "我还没听懂这句话" in (result.response_text or "")


@pytest.mark.asyncio
async def test_conversation_service_records_failure_when_kernel_raises() -> None:
    recorder = FakeMessageEventRecorder()
    service = _build_service(recorder=recorder, planner=FakePlanner(raises=True))

    with pytest.raises(RuntimeError):
        await service.handle_inbound_message(
            HandleInboundConversationMessageCommand(
                channel="web",
                message_type="text",
                user_identity="user-1",
                external_message_id=None,
                root_message_id=None,
                parent_message_id=None,
                chat_id=None,
                thread_id=None,
                text="你好",
                raw_payload={"text": "你好"},
            )
        )

    record = recorder.records[0]
    assert isinstance(record, MessageEventRecord)
    assert record.success is False
    assert record.error_code == "RuntimeError"
    assert record.metadata["reason"] == "handler_exception"


@pytest.mark.asyncio
async def test_conversation_service_uses_llm_fallback_reply_when_kernel_returns_none() -> None:
    recorder = FakeMessageEventRecorder()
    fallback_gateway = FakeFallbackLLMGateway(
        '{"reply_text":"是的，我现在主要帮你处理提醒、待办和记忆。"}'
    )
    service = _build_service(
        recorder=recorder,
        planner=FakePlanner(
            AssistantActionPlan(
                intent="unknown",
                action=None,
                object_type=None,
                object_id=None,
                status="unsupported",
            )
        ),
        executor=FakeExecutor(None),
        fallback_responder=LLMConversationFallbackResponder(
            llm_gateway=fallback_gateway,
            model="gpt-test",
            api_key_suffix="90abcdef",
            history_reader=FakeHistoryReader(),
        ),
    )

    result = await service.handle_inbound_message(
        HandleInboundConversationMessageCommand(
            channel="web",
            message_type="text",
            user_identity="user-1",
            external_message_id=None,
            root_message_id=None,
            parent_message_id=None,
            chat_id=None,
            thread_id=None,
            text="是吗？",
            raw_payload={"text": "是吗？"},
        )
    )

    assert result.handled is True
    assert result.handled_by == "conversation"
    assert result.reason == "llm_fallback_replied"
    assert result.response_text == "是的，我现在主要帮你处理提醒、待办和记忆。"
    assert fallback_gateway.last_request is not None
    assert "最近对话：" in fallback_gateway.last_request.prompt
    record = recorder.records[0]
    assert isinstance(record, MessageEventRecord)
    assert record.metadata["handled"] is True
    assert record.metadata["reason"] == "llm_fallback_replied"
