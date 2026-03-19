from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    OutboundMessage,
    SendResult,
)


def test_messaging_contract_models_are_constructible() -> None:
    target = MessageTarget(channel="im", recipient_id="user-1")
    message = OutboundMessage(text="测试提醒")
    result = SendResult(accepted=True, external_message_id="msg-1")

    assert target.channel == "im"
    assert message.text == "测试提醒"
    assert result.accepted is True
