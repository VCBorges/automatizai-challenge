"""
Base exception classes for the application.

This module defines the exception hierarchy that should be used throughout
the application. All custom exceptions should inherit from these base classes.
"""

from typing import Any


class ApplicationError(Exception):
    default_message: str = "An unexpected error occurred"
    default_code: str = "application_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        self.message = message or self.default_message
        self.code = code or self.default_code
        self.details = details or {}
        super().__init__(self.message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class ResourceNotFoundError(ApplicationError):
    default_message = "Resource not found"
    default_code = "resource_not_found"

    def __init__(
        self,
        message: str | None = None,
        *,
        resource_type: str | None = None,
        resource_id: str | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if resource_type:
            details["resource_type"] = resource_type
        if resource_id:
            details["resource_id"] = resource_id

        super().__init__(message, code=code, details=details)


class ExternalServiceError(ApplicationError):
    default_message = "External service error"
    default_code = "external_service_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        service_name: str | None = None,
        original_error: Exception | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if service_name:
            details["service_name"] = service_name
        if original_error:
            details["original_error"] = str(original_error)
            details["original_error_type"] = type(original_error).__name__

        super().__init__(message, code=code, details=details)
        self.original_error = original_error


class ValidationError(ApplicationError):
    default_message = "Validation error"
    default_code = "validation_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        field: str | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        details = details or {}
        if field:
            details["field"] = field

        super().__init__(message, code=code, details=details)


class ProcessingError(ApplicationError):
    default_message = "Processing error"
    default_code = "processing_error"

