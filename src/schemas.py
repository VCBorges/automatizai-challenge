import typing as tp
import uuid
from datetime import datetime

from fastapi import File, UploadFile
from pydantic import Field, model_validator

from src import enums
from src.core.base.schemas import BaseSchema


class AnalysisCreateInput(BaseSchema):
    company_name: str = Field(
        description="Company name provided by the client as the owner of the uploaded documents.",
    )
    contrato_social: tp.Annotated[
        UploadFile | None,
        File(
            default=None,
            description="Contrato social PDF file.",
            media_type="application/pdf",
        ),
    ]
    cartao_cnpj: tp.Annotated[
        UploadFile | None,
        File(
            default=None,
            description="Cartão CNPJ PDF file.",
            media_type="application/pdf",
        ),
    ]
    certidao_negativa: tp.Annotated[
        UploadFile | None,
        File(
            default=None,
            description="Certidão negativa PDF file.",
            media_type="application/pdf",
        ),
    ]

    @model_validator(mode="after")
    def validate_at_least_one_document(self) -> tp.Self:
        if not any(
            [
                self.contrato_social,
                self.cartao_cnpj,
                self.certidao_negativa,
            ]
        ):
            raise ValueError("At least one document must be provided.")
        return self


class AnalysisCreateResponse(BaseSchema):
    job_id: uuid.UUID = Field(description="ID of the created analysis job.")
    status: enums.AnalysisStatus = Field(
        description="Initial status for the analysis job."
    )


class AnalysisInconsistencyOut(BaseSchema):
    id: uuid.UUID = Field(description="Inconsistency unique identifier.")
    code: str = Field(description="Stable inconsistency code (e.g., cnpj_mismatch).")
    severity: enums.InconsistencySeverity = Field(
        description="Severity of the inconsistency."
    )
    message: str = Field(description="Human-readable explanation of the inconsistency.")
    pointers: dict | None = Field(
        default=None,
        description="Structured pointers/evidence (document_type/field/evidence).",
    )
    document_id: uuid.UUID | None = Field(
        default=None,
        description="Optional document id that originated this inconsistency.",
    )


class DocumentOut(BaseSchema):
    id: uuid.UUID = Field(description="Document unique identifier.")
    document_type: enums.DocumentType = Field(description="Type of the document.")
    filename: str = Field(description="Original filename provided by the client.")
    content_type: str = Field(description="MIME type provided by the client.")
    size_bytes: int | None = Field(
        default=None,
        description="Size of the PDF in bytes.",
    )
    checksum_sha256: str | None = Field(
        default=None,
        description="SHA-256 checksum of the PDF content.",
    )
    object_key: str = Field(description="Object key/path for the stored PDF.")
    extracted_text: str | None = Field(
        default=None,
        description="Extracted raw text content from the PDF.",
    )
    extracted_data: dict | None = Field(
        default=None,
        description="Structured fields extracted from the document (normalized JSON).",
    )
    llm_model: str | None = Field(
        default=None,
        description="LLM model identifier used for extraction (via LangGraph/OpenRouter).",
    )
    created_at: datetime = Field(
        description="Timestamp when this document was created."
    )
    updated_at: datetime = Field(
        description="Timestamp when this document was last updated."
    )


class AnalysisJobOut(BaseSchema):
    id: uuid.UUID = Field(description="Analysis job identifier.")
    company_name: str = Field(
        description="Company name provided by the client as the owner of the uploaded documents.",
    )
    status: enums.AnalysisStatus = Field(description="Current job status.")
    decision: enums.AnalysisDecision | None = Field(
        default=None,
        description="Final decision when the job is SUCCEEDED.",
    )
    error_message: str | None = Field(
        default=None,
        description="Error message when the job is FAILED.",
    )
    error_details: dict | None = Field(
        default=None,
        description="Structured error details when the job is FAILED.",
    )
    finished_at: datetime | None = Field(
        default=None,
        description="Timestamp when the job finished (succeeded or failed).",
    )
    created_at: datetime = Field(description="Timestamp when the job was created.")
    updated_at: datetime = Field(description="Timestamp when the job was last updated.")
    documents: list[DocumentOut] = Field(
        default_factory=list,
        description="Documents attached to this analysis job.",
    )
    inconsistencies: list[AnalysisInconsistencyOut] = Field(
        default_factory=list,
        description="Inconsistencies found during validation.",
    )
