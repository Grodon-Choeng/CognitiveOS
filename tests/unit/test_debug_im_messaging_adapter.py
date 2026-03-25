import pytest

from app.infrastructure.integrations.messaging.base import MessageTarget, OutboundMessage
from app.infrastructure.integrations.messaging.debug_im_adapter import DebugIMMessagingAdapter
from app.infrastructure.integrations.messaging.router import RoutingMessagingAdapter


@pytest.mark.asyncio
async def test_debug_im_messaging_adapter_generates_message_id() -> None:
    adapter = DebugIMMessagingAdapter()

    result = await adapter.send_message(
        MessageTarget(channel="debug_im", recipient_id="debug-user"),
        OutboundMessage(text="你好"),
    )

    assert result.accepted is True
    assert result.external_message_id is not None
    assert result.external_message_id.startswith("dbgout_")
    assert result.metadata["adapter"] == "debug_im"


@pytest.mark.asyncio
async def test_routing_messaging_adapter_uses_debug_im_adapter() -> None:
    adapter = DebugIMMessagingAdapter()
    router = RoutingMessagingAdapter(
        default_adapter=adapter,
        debug_im_adapter=adapter,
    )

    result = await router.send_message(
        MessageTarget(channel="debug_im", recipient_id="debug-user"),
        OutboundMessage(text="你好"),
    )

    assert result.external_message_id is not None
    assert result.external_message_id.startswith("dbgout_")
