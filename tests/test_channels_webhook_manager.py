from app.channels import IMManager, IMMessage, MessageType
from app.config import IMConfig
from app.enums import IMProvider


def test_im_manager_returns_none_for_disabled_provider():
    manager = IMManager(
        [
            IMConfig(provider=IMProvider.FEISHU, webhook_url="https://example.com", enabled=False),
        ]
    )

    adapter = manager.get_adapter(IMProvider.FEISHU)
    assert adapter is None


def test_im_manager_tracks_enabled_provider():
    manager = IMManager(
        [
            IMConfig(provider=IMProvider.DISCORD, webhook_url="https://example.com", enabled=True),
        ]
    )

    providers = manager.get_available_providers()
    assert providers == [IMProvider.DISCORD]


def test_message_defaults_to_text():
    message = IMMessage(content="hello")

    assert message.msg_type == MessageType.TEXT
