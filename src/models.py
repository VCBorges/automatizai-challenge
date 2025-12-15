import uuid
from datetime import datetime

from sqlalchemy import Column, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlmodel import Field, Relationship

from src import enums
from src.core.base.models import DBModel


class AnalysisJob(DBModel, table=True):
    __tablename__ = "analysis_jobs"

    company_name: str | None = Field(
        default=None,
        index=True,
        description="Company name provided by the client as the owner of the uploaded documents.",
    )
    status: enums.AnalysisStatus = Field(
        default=enums.AnalysisStatus.PENDING,
        index=True,
        description="Current status of the analysis job lifecycle.",
    )
    decision: enums.AnalysisDecision | None = Field(
        default=None,
        index=True,
        description="Final decision for the analysis job, present when status is SUCCEEDED.",
    )
    error_message: str | None = Field(
        default=None,
        description="Human-readable technical error message when the job fails.",
    )
    error_details: dict | None = Field(
        default=None,
        sa_column=Column(JSONB),
        description="Structured error details for debugging/auditing when the job fails.",
    )
    finished_at: datetime | None = Field(
        default=None,
        index=True,
        sa_type=DateTime(timezone=True),
        description="Timestamp when the job finished (succeeded or failed).",
    )

    # Relationships
    documents: list["Document"] = Relationship(back_populates="job")
    inconsistencies: list["AnalysisInconsistency"] = Relationship(back_populates="job")


class Document(DBModel, table=True):
    __tablename__ = "documents"

    document_type: enums.DocumentType = Field(
        index=True,
        description="Type of the uploaded document for this analysis job.",
    )
    filename: str = Field(
        description="Original filename provided by the client.",
    )
    content_type: str = Field(
        description="MIME content type provided by the client for the uploaded PDF.",
    )
    size_bytes: int | None = Field(
        default=None,
        description="Size of the uploaded PDF in bytes.",
    )
    checksum_sha256: str | None = Field(
        default=None,
        index=True,
        description="SHA-256 checksum of the uploaded PDF content for deduplication/auditing.",
    )

    object_key: str = Field(
        description="Object key/path for the original PDF file in the configured storage.",
    )
    extracted_text: str | None = Field(
        default=None,
        sa_column=Column(Text),
        description="Extracted raw text content from the PDF (if extracted successfully).",
    )

    extracted_data: dict | None = Field(
        default=None,
        sa_column=Column(JSONB),
        description="Structured fields extracted from this document (normalized JSON).",
    )
    llm_model: str | None = Field(
        default=None,
        description="LLM model identifier used for extraction (via LangGraph/OpenRouter).",
    )

    # Foreign keys
    job_id: uuid.UUID = Field(
        foreign_key="analysis_jobs.id",
        index=True,
        description="FK to the analysis job that owns this document.",
    )

    # Relationships
    job: AnalysisJob = Relationship(back_populates="documents")


class AnalysisInconsistency(DBModel, table=True):
    __tablename__ = "analysis_inconsistencies"

    code: str = Field(
        index=True,
        description="Stable machine-readable inconsistency code (e.g., cnpj_mismatch, certificate_expired).",
    )
    severity: enums.InconsistencySeverity = Field(
        index=True,
        description="Severity of the inconsistency: BLOCKER (fails approval) or WARN (needs review).",
    )
    message: str = Field(
        description="Human-readable explanation of the inconsistency.",
    )
    pointers: dict | None = Field(
        default=None,
        sa_column=Column(JSONB),
        description="Structured pointers to where the inconsistency came from (document_type/field/evidence).",
    )

    # Foreign keys
    job_id: uuid.UUID = Field(
        foreign_key="analysis_jobs.id",
        index=True,
        description="FK to the analysis job that owns this inconsistency.",
    )
    document_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="documents.id",
        index=True,
        description="Optional FK to the specific document that originated this inconsistency.",
    )

    # Relationships
    job: AnalysisJob = Relationship(back_populates="inconsistencies")
