from app.application.conversations.kernel.renderer import AssistantResponseRenderer
from app.application.conversations.kernel.results import (
    AssistantDisambiguationResult,
    AssistantExecutionResult,
)
from app.application.conversations.kernel.state import AssistantTurnContext


def _empty_turn_context() -> AssistantTurnContext:
    return AssistantTurnContext(
        conversation_id="conversation-1",
        session_id="session-1",
        latest_user_text=None,
    )


def test_renderer_formats_create_reminder_naturally() -> None:
    renderer = AssistantResponseRenderer()
    result = AssistantExecutionResult(
        success=True,
        action="create_reminder",
        object_type="reminder",
        object_id="r-1",
        object_title="买药",
        payload={
            "when": "2026-03-25T09:00:00+08:00",
            "timezone": "Asia/Shanghai",
        },
    )

    text = renderer.render(result, turn_context=_empty_turn_context())

    assert "已经记成提醒了" in text
    assert "买药" in text
    assert "2026-03-25 09:00" in text


def test_renderer_formats_task_search_with_followup_hint() -> None:
    renderer = AssistantResponseRenderer()
    result = AssistantExecutionResult(
        success=True,
        action="list_tasks",
        object_type="task",
        payload={
            "query": "纪要",
            "items": [
                {
                    "object_type": "task",
                    "object_id": "t-1",
                    "title": "整理纪要",
                    "status": "pending",
                }
            ],
        },
    )

    text = renderer.render(result, turn_context=_empty_turn_context())

    assert "匹配“纪要”的任务" in text
    assert "整理纪要" in text
    assert "完成第二个" in text or "取消第一个" in text


def test_renderer_formats_disambiguation_choices() -> None:
    renderer = AssistantResponseRenderer()
    result = AssistantDisambiguationResult(
        prompt="我找到几个可能的对象，你想操作哪一个？",
        candidates=[
            {"object_type": "reminder", "object_id": "r-1", "title": "买药"},
            {"object_type": "reminder", "object_id": "r-2", "title": "买水果"},
        ],
    )

    text = renderer.render(result, turn_context=_empty_turn_context())

    assert "我找到几个可能的对象" in text
    assert "1. 买药" in text
    assert "2. 买水果" in text
    assert "第一个" in text


def test_renderer_formats_working_set_view() -> None:
    renderer = AssistantResponseRenderer()
    result = AssistantExecutionResult(
        success=True,
        action="show_overview",
        payload={
            "view": "working_set",
            "pending_tasks": [{"object_type": "task", "object_id": "t-1", "title": "整理周报"}],
            "pending_reminders": [
                {"object_type": "reminder", "object_id": "r-1", "title": "买药提醒"}
            ],
            "active_memories": [{"object_type": "memory", "object_id": "m-1", "title": "提醒偏好"}],
            "focused_object": {"object_type": "task", "object_id": "t-1", "title": "整理周报"},
            "last_assistant_action": {"action_type": "list_tasks", "summary": "刚给你列出待办"},
        },
    )

    text = renderer.render(result, turn_context=_empty_turn_context())

    assert "最近我主要在处理这些" in text
    assert "当前焦点：整理周报" in text


def test_renderer_formats_scoped_memory_reply() -> None:
    renderer = AssistantResponseRenderer()
    result = AssistantExecutionResult(
        success=True,
        action="create_memory",
        object_type="memory",
        object_id="m-1",
        object_title="客户偏好邮件沟通",
        payload={
            "memory_type": "context",
            "scope_object_type": "task",
        },
    )

    text = renderer.render(result, turn_context=_empty_turn_context())

    assert "背景记到这个待办里了" in text
