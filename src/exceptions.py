from src.core.base.exceptions import (
    ExternalServiceError,
    ProcessingError,
    ResourceNotFoundError,
    ValidationError,
)
from src.core.types import DictStrAny


class AnalysisJobNotFoundError(ResourceNotFoundError):
    default_message = "Analysis job not found"
    default_code = "analysis_job_not_found"

    def __init__(
        self,
        job_id: str | None = None,
        *,
        message: str | None = None,
        details: DictStrAny | None = None,
    ) -> None:
        super().__init__(
            message,
            resource_type="AnalysisJob",
            resource_id=job_id,
            code=self.default_code,
            details=details,
        )


class DocumentNotFoundError(ResourceNotFoundError):
    default_message = "Document not found"
    default_code = "document_not_found"

    def __init__(
        self,
        document_id: str | None = None,
        *,
        message: str | None = None,
        details: DictStrAny | None = None,
    ) -> None:
        super().__init__(
            message,
            resource_type="Document",
            resource_id=document_id,
            code=self.default_code,
            details=details,
        )


class LLMServiceError(ExternalServiceError):
    default_message = "LLM service error"
    default_code = "llm_service_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        original_error: Exception | None = None,
        details: DictStrAny | None = None,
    ) -> None:
        super().__init__(
            message,
            service_name="LLM",
            original_error=original_error,
            code=self.default_code,
            details=details,
        )


class StorageServiceError(ExternalServiceError):
    default_message = "Storage service error"
    default_code = "storage_service_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        object_key: str | None = None,
        original_error: Exception | None = None,
        details: DictStrAny | None = None,
    ) -> None:
        details = details or {}
        if object_key:
            details["object_key"] = object_key

        super().__init__(
            message,
            service_name="Storage",
            original_error=original_error,
            code=self.default_code,
            details=details,
        )


class LLMExtractionError(ProcessingError):
    default_message = "LLM extraction failed to produce a result"
    default_code = "llm_extraction_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        extractor_name: str | None = None,
        document_type: str | None = None,
        details: DictStrAny | None = None,
    ) -> None:
        details = details or {}
        if extractor_name:
            details["extractor_name"] = extractor_name
        if document_type:
            details["document_type"] = document_type

        super().__init__(message, code=self.default_code, details=details)


class PDFExtractionError(ProcessingError):
    default_message = "PDF text extraction failed"
    default_code = "pdf_extraction_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        file_path: str | None = None,
        original_error: Exception | None = None,
        details: DictStrAny | None = None,
    ) -> None:
        details = details or {}
        if file_path:
            details["file_path"] = file_path
        if original_error:
            details["original_error"] = str(original_error)
            details["original_error_type"] = type(original_error).__name__

        super().__init__(message, code=self.default_code, details=details)
        self.original_error = original_error


class DocumentAnalysisError(ProcessingError):
    default_message = "Document analysis failed"
    default_code = "document_analysis_error"

    def __init__(
        self,
        message: str | None = None,
        *,
        job_id: str | None = None,
        original_error: Exception | None = None,
        details: DictStrAny | None = None,
    ) -> None:
        details = details or {}
        if job_id:
            details["job_id"] = job_id
        if original_error:
            details["original_error"] = str(original_error)
            details["original_error_type"] = type(original_error).__name__

        super().__init__(message, code=self.default_code, details=details)
        self.original_error = original_error


class InvalidDocumentTypeError(ValidationError):
    default_message = "Invalid document type"
    default_code = "invalid_document_type"

    def __init__(
        self,
        message: str | None = None,
        *,
        document_type: str | None = None,
        expected_types: list[str] | None = None,
        details: DictStrAny | None = None,
    ) -> None:
        details = details or {}
        if document_type:
            details["provided_type"] = document_type
        if expected_types:
            details["expected_types"] = expected_types

        super().__init__(
            message, field="document_type", code=self.default_code, details=details
        )
