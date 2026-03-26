from collections.abc import Callable
from datetime import datetime

from app.application.conversations.kernel.results import (
    AssistantConfirmationResult,
    AssistantDisambiguationResult,
    AssistantExecutionResult,
)
from app.application.conversations.kernel.state import AssistantTurnContext


class AssistantResponseRenderer:
    def render(
        self,
        result: (
            AssistantExecutionResult | AssistantDisambiguationResult | AssistantConfirmationResult
        ),
        *,
        turn_context: AssistantTurnContext,
    ) -> str:
        if isinstance(result, AssistantDisambiguationResult):
            lines = [result.prompt]
            for index, candidate in enumerate(result.candidates, start=1):
                lines.append(f"{index}. {candidate['title']}")
            lines.append("你可以直接说“第一个”或把标题再说完整一点。")
            return "\n".join(lines)

        if isinstance(result, AssistantConfirmationResult):
            lines = [result.prompt]
            if result.preview_text:
                lines.append(f"我当前理解的是“{result.preview_text}”。")
            lines.append("如果没问题，你可以直接回复“是的”或再说得更具体一点。")
            return "\n".join(lines)

        if result.message_hint:
            return result.message_hint
        return _render_execution_result(result, turn_context=turn_context)


def _render_execution_result(
    result: AssistantExecutionResult,
    *,
    turn_context: AssistantTurnContext,
) -> str:
    if result.action == "reply_greeting":
        return "你好，我在。你可以让我记提醒、建待办、记住偏好，也可以直接问我今天还有什么。"
    if result.action == "show_help":
        return (
            "我现在主要能帮你做四类事：提醒、待办、记忆和概览。\n"
            "你可以直接说“明天提醒我买药”“待办：整理周报”“记一下我不喜欢早上八点前提醒”或“看看今天还有什么”。"
        )
    if result.action == "show_activity":
        activities = result.payload.get("recent_activity")
        if not isinstance(activities, list) or not activities:
            return "这会儿还没有最近活动。"
        lines = ["最近这几步我帮你处理的是："]
        for activity in activities:
            if isinstance(activity, dict):
                summary = activity.get("summary")
                if isinstance(summary, str):
                    lines.append(f"- {summary}")
        return "\n".join(lines)
    if result.action == "show_overview":
        reminders = _payload_items(result.payload, "pending_reminders")
        tasks = _payload_items(result.payload, "pending_tasks")
        memories = _payload_items(result.payload, "active_memories")
        overview_view = _optional_str(result.payload.get("view"))
        if overview_view == "working_set":
            return _render_working_set_view(result)
        lines = [
            "我先帮你看了一眼今天的情况："
            if overview_view == "today"
            else "我先帮你看了一眼当前会话："
        ]
        lines.append(f"- 待办提醒 {len(reminders)} 个")
        lines.append(f"- 待办任务 {len(tasks)} 个")
        lines.append(f"- 活跃记忆 {len(memories)} 条")
        lines.append("你可以继续说“查看待办”“查看提醒”或“查看记忆”。")
        return "\n".join(lines)
    if result.action == "create_task":
        return (
            f"好，已经记成待办了。\n内容是“{result.object_title}”。\n"
            "如果你愿意，我也可以马上帮你看一下当前待办列表。"
        )
    if result.action == "complete_task":
        return (
            f"好，已经帮你完成这个待办了。\n待办是“{result.object_title}”。\n"
            "你可以继续说“查看待办”看看还剩什么。"
        )
    if result.action == "cancel_task":
        return (
            f"好，这个待办我已经取消了。\n待办是“{result.object_title}”。\n"
            "如果你想，我也可以继续帮你整理剩下的待办。"
        )
    if result.action == "create_reminder":
        payload = result.payload
        when = _format_when(payload.get("when"), payload.get("timezone"))
        return (
            "好，已经记成提醒了。\n"
            f"时间是 {when}，内容是“{result.object_title}”。\n"
            "之后你也可以直接说“取消这个提醒”。"
        )
    if result.action == "cancel_reminder":
        return (
            f"好，这条提醒我已经取消了。\n提醒内容是“{result.object_title}”。\n"
            "如果你要改时间，也可以直接重新告诉我。"
        )
    if result.action == "cancel_all_reminders":
        total_canceled = int(result.payload.get("total_canceled", 0) or 0)
        if total_canceled <= 0:
            return "当前没有可取消的提醒。"
        one_off_canceled = int(result.payload.get("one_off_canceled", 0) or 0)
        recurring_canceled = int(result.payload.get("recurring_canceled", 0) or 0)
        lines = [f"好，当前会话里可见的提醒我已经全部取消了，共 {total_canceled} 条。"]
        if one_off_canceled:
            lines.append(f"- 单次提醒 {one_off_canceled} 条")
        if recurring_canceled:
            lines.append(f"- 循环提醒 {recurring_canceled} 条")
        lines.append("你可以继续说“查看提醒”确认现在还剩什么。")
        return "\n".join(lines)
    if result.action == "reschedule_reminder":
        payload = result.payload
        when = _format_when(payload.get("when"), payload.get("timezone"))
        change_kind = _optional_str(payload.get("change_kind"))
        if change_kind == "content":
            return (
                f"好，这条提醒我已经改成“{result.object_title}”了。\n"
                f"时间仍然是 {when}。\n"
                "如果还要再改时间或内容，也可以直接继续说。"
            )
        return (
            "好，这条提醒我已经帮你改时间了。\n"
            f"新的时间是 {when}，内容还是“{result.object_title}”。\n"
            "如果还要再改，也可以直接继续说。"
        )
    if result.action == "complex_plan_preview":
        preview_items = result.payload.get("preview_items")
        lines = ["我理解成以下动作，请确认："]
        if isinstance(preview_items, list):
            for index, item in enumerate(preview_items, start=1):
                if isinstance(item, str):
                    lines.append(f"{index}. {item}")
        lines.append("如果没问题，你可以直接回复“确认”或“按这个来”。")
        return "\n".join(lines)
    if result.action == "complex_plan_executed":
        recurring_reminders = _payload_items(result.payload, "created_recurring_reminders")
        one_off_reminders = _payload_items(result.payload, "created_one_off_reminders")
        memory_items = _payload_items(result.payload, "memory")
        lines = ["我已经按这个方案建好了。"]
        if recurring_reminders:
            lines.append(f"- 已创建 {len(recurring_reminders)} 条循环提醒")
        if one_off_reminders:
            lines.append(f"- 已创建 {len(one_off_reminders)} 条单次提醒")
        if memory_items:
            lines.append("- 已把“另行通知”这类约束记成偏好，避免误建提醒")
        return "\n".join(lines)
    if result.action == "retry_failed_reminder":
        return (
            "好，我已经重新尝试启动这条失败提醒了。\n"
            f"提醒内容是“{result.object_title}”。\n"
            "你可以继续说“查看失败提醒”确认还有没有没恢复的。"
        )
    if result.action == "create_memory":
        memory_type = _optional_str(result.payload.get("memory_type"))
        scope_object_type = _optional_str(result.payload.get("scope_object_type"))
        if scope_object_type:
            return (
                f"好，我已经把这条{_memory_type_label(memory_type)}记到{_scope_label(scope_object_type)}里了。\n"
                f"内容是“{result.object_title}”。\n"
                "如果你愿意，我也可以继续帮你看这个对象的上下文。"
            )
        return (
            f"好，这条{_memory_type_label(memory_type)}我记下了。\n"
            f"内容是“{result.object_title}”。\n"
            "以后你也可以让我把类似偏好继续记起来。"
        )
    if result.action == "archive_memory":
        return (
            "好，这条记忆我已经归档了。\n"
            f"内容是“{result.object_title}”。\n"
            "如果还要看其他记忆，也可以直接说“查看记忆”。"
        )
    if result.action == "convert_task_to_reminder":
        reminder_items = _payload_items(result.payload, "reminder")
        reminder_text = (
            reminder_items[0]["title"] if reminder_items else result.object_title or "这条待办"
        )
        return (
            "好，我已经把这条待办挂上提醒了。\n"
            f"待办是“{result.object_title}”，提醒内容是“{reminder_text}”。\n"
            "你可以继续说“查看提醒”或“查看待办”。"
        )
    if result.action == "convert_reminder_to_task":
        task_items = _payload_items(result.payload, "task")
        task_text = task_items[0]["title"] if task_items else result.object_title or "这条提醒"
        return (
            "好，我已经把这条提醒改成待办了。\n"
            f"新的待办是“{task_text}”。\n"
            "你可以继续说“查看待办”确认一下。"
        )
    if result.action == "list_tasks":
        query = _optional_str(result.payload.get("query"))
        status = _optional_str(result.payload.get("status"))
        return _render_list_result(
            result=result,
            empty_text=f"当前没有{_build_filtered_title('任务', status, query)}。",
            header_builder=lambda count: _build_list_header(
                noun="任务",
                count=count,
                status=status,
                query=query,
                default_header=f"你现在还有 {count} 个待办：",
            ),
            line_builder=lambda index, item: f"{index}. {item['title']}",
            followup_hint="你可以直接说“完成第二个”或“取消第一个”。",
        )
    if result.action == "list_reminders":
        query = _optional_str(result.payload.get("query"))
        status = _optional_str(result.payload.get("status"))
        return _render_list_result(
            result=result,
            empty_text=f"当前没有{_build_filtered_title('提醒', status, query)}。",
            header_builder=lambda count: _build_list_header(
                noun="提醒",
                count=count,
                status=status,
                query=query,
                default_header=f"你现在有 {count} 个提醒：",
            ),
            line_builder=lambda index, item: (
                f"{index}. {_reminder_schedule_prefix(item)}{item['title']}（"
                f"{_format_when(item.get('when'), item.get('timezone'))}）"
            ),
            followup_hint="你可以直接说“取消第二个”“取消买药那个提醒”或“取消所有提醒”。",
        )
    if result.action == "list_memories":
        query = _optional_str(result.payload.get("query"))
        status = _optional_str(result.payload.get("status"))
        return _render_list_result(
            result=result,
            empty_text=f"当前没有{_build_filtered_title('记忆', status, query)}。",
            header_builder=lambda count: _build_list_header(
                noun="记忆",
                count=count,
                status=status,
                query=query,
                default_header=f"我这边还记着 {count} 条信息：",
            ),
            line_builder=lambda index, item: f"{index}. {item['title']}",
            followup_hint="你可以直接说“归档第一个”。",
        )
    return "这一步已经处理好了。"


def _render_list_result(
    *,
    result: AssistantExecutionResult,
    empty_text: str,
    header_builder: Callable[[int], str],
    line_builder: Callable[[int, dict[str, str]], str],
    followup_hint: str,
) -> str:
    items = _payload_items(result.payload, "items")
    if not items:
        return empty_text
    lines = [header_builder(len(items))]
    for index, item in enumerate(items, start=1):
        lines.append(line_builder(index, item))
    lines.append(followup_hint)
    return "\n".join(lines)


def _payload_items(payload: dict[str, object], key: str) -> list[dict[str, str]]:
    raw_items = payload.get(key)
    if isinstance(raw_items, dict):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, str]] = []
    for item in raw_items:
        if isinstance(item, dict):
            normalized_item: dict[str, str] = {}
            for item_key, item_value in item.items():
                if isinstance(item_key, str) and isinstance(item_value, str):
                    normalized_item[item_key] = item_value
            if normalized_item:
                items.append(normalized_item)
    return items


def _reminder_schedule_prefix(item: dict[str, str]) -> str:
    schedule_kind = item.get("schedule_kind")
    schedule_label = item.get("schedule_label")
    if schedule_kind == "recurring":
        if isinstance(schedule_label, str) and schedule_label:
            return f"[循环 {schedule_label}] "
        return "[循环] "
    return "[单次] "


def _render_working_set_view(result: AssistantExecutionResult) -> str:
    reminders = _payload_items(result.payload, "pending_reminders")
    tasks = _payload_items(result.payload, "pending_tasks")
    memories = _payload_items(result.payload, "active_memories")
    focused_object = result.payload.get("focused_object")
    last_action = result.payload.get("last_assistant_action")
    lines = ["这会话里最近我主要在处理这些："]
    if isinstance(focused_object, dict):
        title = focused_object.get("title")
        if isinstance(title, str) and title:
            lines.append(f"- 当前焦点：{title}")
    if isinstance(last_action, dict):
        summary = last_action.get("summary")
        if isinstance(summary, str) and summary:
            lines.append(f"- 最近动作：{summary}")
    lines.append(f"- 待办任务 {len(tasks)} 个")
    lines.append(f"- 待办提醒 {len(reminders)} 个")
    lines.append(f"- 活跃记忆 {len(memories)} 条")
    lines.append("你可以继续说“第二个”“那个”或直接描述你想改哪条。")
    return "\n".join(lines)


def _format_when(when: object, timezone: object) -> str:
    if not isinstance(when, str):
        return "未提供时间"
    try:
        parsed = datetime.fromisoformat(when)
    except ValueError:
        return when
    timezone_text = timezone if isinstance(timezone, str) else "本地时区"
    return f"{parsed.strftime('%Y-%m-%d %H:%M')}（{timezone_text}）"


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _build_list_header(
    *,
    noun: str,
    count: int,
    status: str | None,
    query: str | None,
    default_header: str,
) -> str:
    if query:
        return f"我找到 {count} 个匹配“{query}”的{_build_status_title(noun, status)}："
    if status and noun != "任务":
        return f"当前{_build_status_title(noun, status)}有 {count} 个："
    if status and noun == "任务" and status != "pending":
        return f"当前{_build_status_title(noun, status)}有 {count} 个："
    return default_header


def _build_status_title(noun: str, status: str | None) -> str:
    if status == "pending":
        return f"待办{noun}"
    if status == "completed":
        return f"已完成{noun}"
    if status == "canceled":
        return f"已取消{noun}"
    if status == "failed":
        return f"失败{noun}"
    if status == "archived":
        return f"已归档{noun}"
    if status == "active":
        return f"活跃{noun}"
    return noun


def _build_filtered_title(noun: str, status: str | None, query: str | None) -> str:
    title = _build_status_title(noun, status)
    if query is None:
        return title
    return f"匹配“{query}”的{title}"


def _memory_type_label(memory_type: str | None) -> str:
    if memory_type == "preference":
        return "偏好"
    if memory_type == "context":
        return "背景"
    if memory_type == "temporary":
        return "临时信息"
    return "信息"


def _scope_label(scope_object_type: str) -> str:
    if scope_object_type == "task":
        return "这个待办"
    if scope_object_type == "reminder":
        return "这个提醒"
    return "这个对象"
