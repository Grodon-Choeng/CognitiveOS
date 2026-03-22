from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.application.audit.errors import AuditQueryValidationError
from app.application.memory.errors import MemoryNotFoundError
from app.application.reminders.errors import (
    ReminderNotFoundError,
    ReminderStateConflictError,
    ReminderWorkflowCancelError,
    ReminderWorkflowNotStartedError,
    ReminderWorkflowStartError,
)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AuditQueryValidationError)
    async def audit_query_validation_handler(
        _request: Request,
        exc: AuditQueryValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": str(exc)},
        )

    @app.exception_handler(NotImplementedError)
    async def not_implemented_handler(
        _request: Request,
        exc: NotImplementedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            content={"detail": str(exc) or "功能尚未实现。"},
        )

    @app.exception_handler(ReminderNotFoundError)
    async def reminder_not_found_handler(
        _request: Request,
        exc: ReminderNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ReminderWorkflowNotStartedError)
    async def reminder_workflow_not_started_handler(
        _request: Request,
        exc: ReminderWorkflowNotStartedError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ReminderWorkflowStartError)
    async def reminder_workflow_start_handler(
        _request: Request,
        exc: ReminderWorkflowStartError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ReminderWorkflowCancelError)
    async def reminder_workflow_cancel_handler(
        _request: Request,
        exc: ReminderWorkflowCancelError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"detail": str(exc)},
        )

    @app.exception_handler(ReminderStateConflictError)
    async def reminder_state_conflict_handler(
        _request: Request,
        exc: ReminderStateConflictError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": str(exc)},
        )

    @app.exception_handler(MemoryNotFoundError)
    async def memory_not_found_handler(
        _request: Request,
        exc: MemoryNotFoundError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"detail": str(exc)},
        )
