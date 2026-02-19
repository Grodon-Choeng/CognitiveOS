from enum import Enum
from typing import Any


class ErrorCode(str, Enum):
    VALIDATION_ERROR = "VALIDATION_ERROR"
    NOT_FOUND = "NOT_FOUND"
    DUPLICATE_ERROR = "DUPLICATE_ERROR"
    STORAGE_ERROR = "STORAGE_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class AppException(Exception):
    def __init__(
        self,
        code: ErrorCode,
        message: str,
        detail: Any = None,
    ) -> None:
        self.code = code
        self.message = message
        self.detail = detail
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "error": self.code.value,
            "message": self.message,
        }
        if self.detail is not None:
            result["detail"] = self.detail
        return result


class NotFoundException(AppException):
    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=f"{resource} not found",
            detail={"resource": resource, "identifier": str(identifier)},
        )


class StorageException(AppException):
    def __init__(self, operation: str, detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Storage operation failed: {operation}",
            detail=detail,
        )


class DatabaseException(AppException):
    def __init__(self, operation: str, detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.DATABASE_ERROR,
            message=f"Database operation failed: {operation}",
            detail=detail,
        )
