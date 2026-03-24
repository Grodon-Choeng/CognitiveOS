from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.infrastructure.db.models.assistant_turn_state import AssistantTurnStateModel
from app.infrastructure.types import JSONObject


class SQLAlchemyAssistantTurnStateStore:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def load(
        self,
        *,
        conversation_id: str,
        session_id: str,
    ) -> JSONObject | None:
        async with self.session_factory() as session:
            model = await session.get(
                AssistantTurnStateModel,
                {
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                },
            )
            if model is None:
                return None
            return model.state_json

    async def save(
        self,
        *,
        conversation_id: str,
        session_id: str,
        state: JSONObject,
    ) -> None:
        async with self.session_factory() as session:
            model = await session.get(
                AssistantTurnStateModel,
                {
                    "conversation_id": conversation_id,
                    "session_id": session_id,
                },
            )
            if model is None:
                model = AssistantTurnStateModel(
                    conversation_id=conversation_id,
                    session_id=session_id,
                    focused_object_type=_get_optional_str(state, "focused_object", "object_type"),
                    focused_object_id=_get_optional_str(state, "focused_object", "object_id"),
                    dialogue_mode=_get_top_level_str(state, "dialogue_mode") or "normal",
                    last_action_type=_get_optional_str(
                        state,
                        "last_assistant_action",
                        "action_type",
                    ),
                    last_action_success=_get_optional_bool(
                        state,
                        "last_assistant_action",
                        "success",
                    ),
                    visible_candidates_json=_get_top_level_list(state, "visible_candidates"),
                    pending_confirmation_json=_get_top_level_dict(
                        state,
                        "pending_confirmation",
                    ),
                    state_json=state,
                )
                session.add(model)
            else:
                model.focused_object_type = _get_optional_str(
                    state,
                    "focused_object",
                    "object_type",
                )
                model.focused_object_id = _get_optional_str(state, "focused_object", "object_id")
                model.dialogue_mode = _get_top_level_str(state, "dialogue_mode") or "normal"
                model.last_action_type = _get_optional_str(
                    state,
                    "last_assistant_action",
                    "action_type",
                )
                model.last_action_success = _get_optional_bool(
                    state,
                    "last_assistant_action",
                    "success",
                )
                model.visible_candidates_json = _get_top_level_list(state, "visible_candidates")
                model.pending_confirmation_json = _get_top_level_dict(
                    state,
                    "pending_confirmation",
                )
                model.state_json = state
            await session.commit()


def _get_top_level_dict(state: JSONObject, key: str) -> JSONObject | None:
    value = state.get(key)
    return value if isinstance(value, dict) else None


def _get_top_level_list(state: JSONObject, key: str) -> list[JSONObject] | None:
    value = state.get(key)
    if not isinstance(value, list):
        return None
    normalized: list[JSONObject] = []
    for item in value:
        if isinstance(item, dict):
            normalized.append(item)
    return normalized or None


def _get_top_level_str(state: JSONObject, key: str) -> str | None:
    value = state.get(key)
    return value if isinstance(value, str) else None


def _get_optional_str(state: JSONObject, parent_key: str, child_key: str) -> str | None:
    parent = state.get(parent_key)
    if not isinstance(parent, dict):
        return None
    value = parent.get(child_key)
    return value if isinstance(value, str) else None


def _get_optional_bool(state: JSONObject, parent_key: str, child_key: str) -> bool:
    parent = state.get(parent_key)
    if not isinstance(parent, dict):
        return True
    value = parent.get(child_key)
    return value if isinstance(value, bool) else True
