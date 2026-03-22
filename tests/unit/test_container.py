from app.bootstrap.container import ApplicationContainer, get_container, reset_container
from app.config.settings import Settings


def test_container_reuses_singletons_for_core_services() -> None:
    container = ApplicationContainer(
        Settings(
            feishu_app_id=None,
            feishu_app_secret=None,
        )
    )

    assert container.build_reminder_service() is container.build_reminder_service()
    assert container.build_conversation_service() is container.build_conversation_service()
    assert container.build_audit_service() is container.build_audit_service()
    assert container.build_message_event_recorder() is container.build_message_event_recorder()
    assert container.build_messaging_adapter() is container.build_messaging_adapter()
    assert [handler.name for handler in container.build_conversation_handlers()] == [
        "reminder",
        "task",
        "memory",
    ]


def test_reset_container_rebuilds_cached_container() -> None:
    reset_container()
    first = get_container()
    reset_container()
    second = get_container()

    assert first is not second
