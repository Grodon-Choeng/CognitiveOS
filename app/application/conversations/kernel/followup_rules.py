from app.application.conversations.commands import HandleInboundConversationMessageCommand
from app.application.conversations.kernel.plans import AssistantActionPlan
from app.application.conversations.kernel.state import AssistantTurnContext

_REFERENCE_FOLLOWUPS = {
    "这个",
    "那个",
    "刚才那个",
    "就刚才那个",
    "第一个",
    "第二个",
    "最后一个",
    "另一个",
    "不是这个，是另一个",
}
_CONFIRM_YES = {"是", "是的", "对", "对的", "好的", "好"}


def plan_from_dialogue_state(
    command: HandleInboundConversationMessageCommand,
    *,
    turn_context: AssistantTurnContext,
) -> AssistantActionPlan | None:
    if command.message_type != "text" or command.text is None:
        return None
    normalized = command.text.strip()
    if not normalized or turn_context.last_assistant_action is None:
        return None

    if (
        turn_context.dialogue_mode == "confirmation"
        and normalized in _CONFIRM_YES
        and turn_context.focused_object is not None
    ):
        action = turn_context.last_assistant_action.action_type
        return AssistantActionPlan(
            intent=action,
            action=action,
            object_type=turn_context.focused_object.object_type,
            object_id=turn_context.focused_object.object_id,
            confidence=0.96,
            reasoning="rules",
        )

    if normalized in _REFERENCE_FOLLOWUPS and turn_context.visible_candidates:
        action = turn_context.last_assistant_action.action_type
        object_type = turn_context.visible_candidates[0].object_type
        return AssistantActionPlan(
            intent=action,
            action=action,
            object_type=object_type,
            object_id=None,
            args={"reference_text": normalize_followup_reference(normalized)},
            confidence=0.94,
            reasoning="rules",
        )
    return None


def normalize_followup_reference(text: str) -> str:
    if text in {"另一个", "不是这个，是另一个"}:
        return "第二个"
    if text == "就刚才那个":
        return "刚才那个"
    return text
