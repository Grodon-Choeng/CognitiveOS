from typing import Any

from app.enums import ErrorCode


class AppError(Exception):
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


AppException = AppError


class NotFoundError(AppError):
    def __init__(self, resource: str, identifier: Any) -> None:
        super().__init__(
            code=ErrorCode.NOT_FOUND,
            message=f"{resource} not found",
            detail={"resource": resource, "identifier": str(identifier)},
        )


NotFoundException = NotFoundError


class ValidationError(AppError):
    def __init__(self, message: str, detail: Any = None) -> None:
        super().__init__(
            code=ErrorCode.VALIDATION_ERROR,
            message=message,
            detail=detail,
        )


ValidationException = ValidationError


class StorageError(AppError):
    def __init__(self, operation: str, detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.STORAGE_ERROR,
            message=f"Storage operation failed: {operation}",
            detail=detail,
        )


StorageException = StorageError


class LLMError(AppError):
    def __init__(self, operation: str, detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.LLM_ERROR,
            message=f"LLM operation failed: {operation}",
            detail=detail,
        )


LLMException = LLMError


class EmbeddingError(AppError):
    def __init__(self, operation: str, detail: str | None = None) -> None:
        super().__init__(
            code=ErrorCode.EMBEDDING_ERROR,
            message=f"Embedding operation failed: {operation}",
            detail=detail,
        )


EmbeddingException = EmbeddingError


class AuthenticationError(AppError):
    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(
            code=ErrorCode.AUTHENTICATION_ERROR,
            message=message,
        )


AuthenticationException = AuthenticationError


class AuthorizationError(AppError):
    def __init__(self, message: str = "Access denied") -> None:
        super().__init__(
            code=ErrorCode.AUTHORIZATION_ERROR,
            message=message,
        )


AuthorizationException = AuthorizationError


class RateLimitError(AppError):
    def __init__(self, retry_after: int | None = None) -> None:
        detail = {"retry_after": retry_after} if retry_after else None
        super().__init__(
            code=ErrorCode.RATE_LIMIT_ERROR,
            message="Rate limit exceeded",
            detail=detail,
        )


RateLimitException = RateLimitError


class InternalError(AppError):
    def __init__(self, message: str = "Internal server error", detail: Any = None) -> None:
        super().__init__(
            code=ErrorCode.INTERNAL_ERROR,
            message=message,
            detail=detail,
        )


InternalException = InternalError
