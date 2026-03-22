from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.http.deps.services import get_reminder_service
from app.api.http.schemas.common import ErrorResponse
from app.api.http.schemas.reminder import (
    CreateReminderRequest,
    ReminderReplyResponse,
    ReminderResponse,
    ReplyReminderRequest,
)
from app.application.reminders.commands import CreateReminderCommand, HandleReminderReplyCommand
from app.application.reminders.service import ReminderApplicationService

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.post(
    "",
    response_model=ReminderResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="创建提醒",
)
async def create_reminder(
    payload: CreateReminderRequest,
    service: Annotated[ReminderApplicationService, Depends(get_reminder_service)],
) -> ReminderResponse:
    command = CreateReminderCommand(
        text=payload.text,
        remind_at=payload.remind_at,
        timezone=payload.timezone,
        conversation_id=payload.conversation_id,
        session_id=payload.session_id,
        source_channel=payload.source_channel,
        source_user_id=payload.source_user_id,
        source_chat_id=payload.source_chat_id,
        source_thread_id=payload.source_thread_id,
        dispatch_channel=payload.dispatch_channel,
        dispatch_recipient_id=payload.dispatch_recipient_id,
        dispatch_chat_id=payload.dispatch_chat_id,
        dispatch_thread_id=payload.dispatch_thread_id,
    )
    result = await service.create_reminder(command)
    return ReminderResponse(**asdict(result))


@router.post(
    "/{reminder_id}/reply",
    response_model=ReminderReplyResponse,
    responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}},
    summary="处理提醒回复",
)
async def reply_to_reminder(
    reminder_id: str,
    payload: ReplyReminderRequest,
    service: Annotated[ReminderApplicationService, Depends(get_reminder_service)],
) -> ReminderReplyResponse:
    command = HandleReminderReplyCommand(
        reminder_id=reminder_id,
        reply_text=payload.reply_text,
    )
    result = await service.handle_reply(command)
    return ReminderReplyResponse(**asdict(result))
