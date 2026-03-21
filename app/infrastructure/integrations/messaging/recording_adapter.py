from time import perf_counter

from app.infrastructure.integrations.messaging.base import (
    MessageTarget,
    MessagingAdapter,
    OutboundMessage,
    SendResult,
)
from app.observability.message_events import MessageEventRecord, MessageEventRecorder


class RecordingMessagingAdapter(MessagingAdapter):
    def __init__(
        self,
        inner: MessagingAdapter,
        recorder: MessageEventRecorder,
    ) -> None:
        self.inner = inner
        self.recorder = recorder

    async def send_message(
        self,
        target: MessageTarget,
        content: OutboundMessage,
    ) -> SendResult:
        started_at = perf_counter()
        metadata = content.metadata

        try:
            result = await self.inner.send_message(target, content)
        except Exception as exc:
            await self.recorder.record(
                MessageEventRecord.create(
                    direction="outbound",
                    channel=target.channel,
                    message_type="text",
                    user_identity=target.recipient_id,
                    external_message_id=None,
                    root_message_id=_get_optional_string(metadata, "root_message_id"),
                    parent_message_id=_get_optional_string(metadata, "parent_message_id"),
                    chat_id=_get_optional_string(metadata, "chat_id"),
                    thread_id=_get_optional_string(metadata, "thread_id"),
                    conversation_id=_get_optional_string(metadata, "conversation_id"),
                    session_id=_get_optional_string(metadata, "session_id"),
                    trace_id=_get_optional_string(metadata, "trace_id"),
                    chain_id=_get_optional_string(metadata, "chain_id"),
                    request_id=_get_optional_string(metadata, "request_id"),
                    text=content.text,
                    success=False,
                    error_code=type(exc).__name__,
                    error_message=str(exc),
                    raw_payload={"text": content.text, "metadata": metadata},
                    metadata=metadata,
                )
            )
            raise

        await self.recorder.record(
            MessageEventRecord.create(
                direction="outbound",
                channel=target.channel,
                message_type="text",
                user_identity=target.recipient_id,
                external_message_id=result.external_message_id,
                root_message_id=_get_optional_string(metadata, "root_message_id"),
                parent_message_id=_get_optional_string(metadata, "parent_message_id"),
                chat_id=_get_optional_string(metadata, "chat_id"),
                thread_id=_get_optional_string(metadata, "thread_id"),
                conversation_id=_get_optional_string(metadata, "conversation_id"),
                session_id=_get_optional_string(metadata, "session_id"),
                trace_id=_get_optional_string(metadata, "trace_id"),
                chain_id=_get_optional_string(metadata, "chain_id"),
                request_id=_get_optional_string(metadata, "request_id"),
                text=content.text,
                raw_payload={
                    "text": content.text,
                    "metadata": metadata,
                    "result_metadata": result.metadata,
                },
                metadata={**metadata, **result.metadata},
            )
        )
        _ = started_at
        return result


def _get_optional_string(payload: object, key: str) -> str | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get(key)
    if isinstance(value, str):
        return value
    return None
