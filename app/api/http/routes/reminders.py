from dataclasses import asdict
from typing import Annotated

from fastapi import APIRouter, Query

from app.api.http.deps import ReminderServiceDep
from app.api.http.schemas.common import ErrorResponse
from app.api.http.schemas.reminder import (
    CreateReminderRequest,
    ReminderListResponse,
    ReminderReplyResponse,
    ReminderResponse,
    ReminderStatusFilter,
    ReplyReminderRequest,
    RescheduleReminderRequest,
)
from app.application.reminders.commands import (
    CancelReminderCommand,
    CreateReminderCommand,
    HandleReminderReplyCommand,
    RescheduleReminderCommand,
)
from app.application.reminders.queries import ListRemindersQuery

router = APIRouter(prefix="/reminders", tags=["reminders"])


@router.get(
    "",
    response_model=ReminderListResponse,
    summary="查询提醒列表",
)
async def list_reminders(
    service: ReminderServiceDep,
    conversation_id: str | None = None,
    session_id: str | None = None,
    status: ReminderStatusFilter | None = None,
    query: str | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ReminderListResponse:
    result = await service.list_reminders(
        ListRemindersQuery(
            conversation_id=conversation_id,
            session_id=session_id,
            status=status,
            query=query,
            limit=limit,
        )
    )
    return ReminderListResponse(
        items=[ReminderResponse(**asdict(reminder)) for reminder in result.items]
    )


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
    service: ReminderServiceDep,
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


@router.get(
    "/{reminder_id}",
    response_model=ReminderResponse,
    responses={404: {"model": ErrorResponse}},
    summary="查询提醒",
)
async def get_reminder(
    reminder_id: str,
    service: ReminderServiceDep,
) -> ReminderResponse:
    result = await service.get_reminder(reminder_id)
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
    service: ReminderServiceDep,
) -> ReminderReplyResponse:
    command = HandleReminderReplyCommand(
        reminder_id=reminder_id,
        reply_text=payload.reply_text,
    )
    result = await service.handle_reply(command)
    return ReminderReplyResponse(**asdict(result))


@router.post(
    "/{reminder_id}/reschedule",
    response_model=ReminderResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="改期提醒",
)
async def reschedule_reminder(
    reminder_id: str,
    payload: RescheduleReminderRequest,
    service: ReminderServiceDep,
) -> ReminderResponse:
    result = await service.reschedule_reminder(
        RescheduleReminderCommand(
            reminder_id=reminder_id,
            text=payload.text,
            remind_at=payload.remind_at,
            timezone=payload.timezone,
        )
    )
    return ReminderResponse(**asdict(result))


@router.post(
    "/{reminder_id}/cancel",
    response_model=ReminderResponse,
    responses={
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        503: {"model": ErrorResponse},
    },
    summary="取消提醒",
)
async def cancel_reminder(
    reminder_id: str,
    service: ReminderServiceDep,
) -> ReminderResponse:
    result = await service.cancel_reminder(CancelReminderCommand(reminder_id=reminder_id))
    return ReminderResponse(**asdict(result))
