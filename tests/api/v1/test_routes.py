import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src import enums, models
from tests.factories import (
    AnalysisInconsistencyFactory,
    AnalysisJobFactory,
    DocumentFactory,
)


@pytest.mark.asyncio
async def test_create_document_analysis_job_returns_202_with_job_id_and_pending_status(
    client: AsyncClient,
    session: AsyncSession,
    contrato_social_pdf: bytes,
    temp_storage_dir: Path,
) -> None:
    """
    When creating an analysis job with valid PDF documents,
    the endpoint returns HTTP 202 with job_id and PENDING status.
    """
    with patch("src.usecases.analysis.celery_app.send_task") as mock_send_task:
        response = await client.post(
            "/v1/analyses",
            data={"company_name": "Tech Solutions LTDA"},
            files={
                "contrato_social": (
                    "contrato.pdf",
                    contrato_social_pdf,
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert data["status"] == enums.AnalysisStatus.PENDING
    assert uuid.UUID(data["job_id"])  # Validates UUID format

    mock_send_task.assert_called_once()


@pytest.mark.asyncio
async def test_create_document_analysis_job_persists_analysis_job_in_database(
    client: AsyncClient,
    session: AsyncSession,
    contrato_social_pdf: bytes,
    temp_storage_dir: Path,
) -> None:
    """
    When creating an analysis job, the AnalysisJob record
    is persisted in the database with correct attributes.
    """
    company_name = "Test Company LTDA"

    with patch("src.usecases.analysis.celery_app.send_task"):
        response = await client.post(
            "/v1/analyses",
            data={"company_name": company_name},
            files={
                "contrato_social": (
                    "contrato.pdf",
                    contrato_social_pdf,
                    "application/pdf",
                )
            },
        )

    job_id = uuid.UUID(response.json()["job_id"])

    stmt = select(models.AnalysisJob).where(models.AnalysisJob.id == job_id)
    result = await session.exec(stmt)
    analysis_job = result.one_or_none()

    assert analysis_job is not None
    assert analysis_job.company_name == company_name
    assert analysis_job.status == enums.AnalysisStatus.PENDING
    assert analysis_job.decision is None
    assert analysis_job.error_message is None
    assert analysis_job.finished_at is None


@pytest.mark.asyncio
async def test_create_document_analysis_job_persists_document_record_for_contrato_social(
    client: AsyncClient,
    session: AsyncSession,
    contrato_social_pdf: bytes,
    temp_storage_dir: Path,
) -> None:
    """
    When uploading a contrato social PDF, a Document record
    is created with correct type and metadata.
    """
    with patch("src.usecases.analysis.celery_app.send_task"):
        response = await client.post(
            "/v1/analyses",
            data={"company_name": "Test Company"},
            files={
                "contrato_social": (
                    "contrato_social.pdf",
                    contrato_social_pdf,
                    "application/pdf",
                )
            },
        )

    job_id = uuid.UUID(response.json()["job_id"])

    stmt = select(models.Document).where(models.Document.job_id == job_id)
    result = await session.exec(stmt)
    documents = result.all()

    assert len(documents) == 1
    document = documents[0]
    assert document.document_type == enums.DocumentType.CONTRATO_SOCIAL
    assert document.filename == "contrato_social.pdf"
    assert document.content_type == "application/pdf"
    assert document.size_bytes == len(contrato_social_pdf)
    assert document.checksum_sha256 is not None
    assert document.object_key is not None


@pytest.mark.asyncio
async def test_create_document_analysis_job_persists_multiple_documents(
    client: AsyncClient,
    session: AsyncSession,
    contrato_social_pdf: bytes,
    cartao_cnpj_pdf: bytes,
    certidao_negativa_pdf: bytes,
    temp_storage_dir: Path,
) -> None:
    """
    When uploading multiple PDF documents, separate Document records
    are created for each document type.
    """
    with patch("src.usecases.analysis.celery_app.send_task"):
        response = await client.post(
            "/v1/analyses",
            data={"company_name": "Full Documents Company"},
            files=[
                (
                    "contrato_social",
                    ("contrato.pdf", contrato_social_pdf, "application/pdf"),
                ),
                ("cartao_cnpj", ("cnpj.pdf", cartao_cnpj_pdf, "application/pdf")),
                (
                    "certidao_negativa",
                    ("certidao.pdf", certidao_negativa_pdf, "application/pdf"),
                ),
            ],
        )

    assert response.status_code == 202
    job_id = uuid.UUID(response.json()["job_id"])

    stmt = select(models.Document).where(models.Document.job_id == job_id)
    result = await session.exec(stmt)
    documents = result.all()

    assert len(documents) == 3

    document_types = {doc.document_type for doc in documents}
    assert document_types == {
        enums.DocumentType.CONTRATO_SOCIAL,
        enums.DocumentType.CARTAO_CNPJ,
        enums.DocumentType.CERTIDAO_NEGATIVA,
    }


@pytest.mark.asyncio
async def test_create_document_analysis_job_stores_pdf_file_in_storage(
    client: AsyncClient,
    session: AsyncSession,
    contrato_social_pdf: bytes,
    temp_storage_dir: Path,
) -> None:
    """
    When uploading a PDF, the file content is stored in the
    configured storage backend.
    """
    with patch("src.usecases.analysis.celery_app.send_task"):
        response = await client.post(
            "/v1/analyses",
            data={"company_name": "Storage Test Company"},
            files={
                "contrato_social": ("test.pdf", contrato_social_pdf, "application/pdf")
            },
        )

    job_id = uuid.UUID(response.json()["job_id"])

    stmt = select(models.Document).where(models.Document.job_id == job_id)
    result = await session.exec(stmt)
    document = result.one()

    # Verify file exists in storage
    stored_file_path = temp_storage_dir / document.object_key
    assert stored_file_path.exists()

    # Verify file content matches
    stored_content = stored_file_path.read_bytes()
    assert stored_content == contrato_social_pdf


@pytest.mark.asyncio
async def test_create_document_analysis_job_enqueues_celery_task_with_job_id(
    client: AsyncClient,
    session: AsyncSession,
    contrato_social_pdf: bytes,
    temp_storage_dir: Path,
) -> None:
    """
    After creating an analysis job, a Celery task is enqueued
    with the correct job_id and correlation_id for async processing.
    """
    with patch("src.usecases.analysis.celery_app.send_task") as mock_send_task:
        response = await client.post(
            "/v1/analyses",
            data={"company_name": "Celery Test Company"},
            files={
                "contrato_social": ("test.pdf", contrato_social_pdf, "application/pdf")
            },
        )

    job_id = response.json()["job_id"]

    mock_send_task.assert_called_once()
    call_kwargs = mock_send_task.call_args.kwargs
    assert call_kwargs["kwargs"]["job_id"] == job_id
    assert "correlation_id" in call_kwargs["kwargs"]
    assert isinstance(call_kwargs["kwargs"]["correlation_id"], str)


@pytest.mark.asyncio
async def test_create_document_analysis_job_fails_without_any_document(
    client: AsyncClient,
    session: AsyncSession,
    temp_storage_dir: Path,
) -> None:
    """
    When no documents are provided, the endpoint returns
    a validation error.
    """
    with patch("src.usecases.analysis.celery_app.send_task"):
        response = await client.post(
            "/v1/analyses",
            data={"company_name": "No Documents Company"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_document_analysis_job_accepts_only_cartao_cnpj(
    client: AsyncClient,
    session: AsyncSession,
    cartao_cnpj_pdf: bytes,
    temp_storage_dir: Path,
) -> None:
    """
    The endpoint accepts a single cartão CNPJ document
    without requiring other document types.
    """
    with patch("src.usecases.analysis.celery_app.send_task"):
        response = await client.post(
            "/v1/analyses",
            data={"company_name": "CNPJ Only Company"},
            files={"cartao_cnpj": ("cnpj.pdf", cartao_cnpj_pdf, "application/pdf")},
        )

    assert response.status_code == 202

    job_id = uuid.UUID(response.json()["job_id"])
    stmt = select(models.Document).where(models.Document.job_id == job_id)
    result = await session.exec(stmt)
    documents = result.all()

    assert len(documents) == 1
    assert documents[0].document_type == enums.DocumentType.CARTAO_CNPJ


@pytest.mark.asyncio
async def test_create_document_analysis_job_accepts_only_certidao_negativa(
    client: AsyncClient,
    session: AsyncSession,
    certidao_negativa_pdf: bytes,
    temp_storage_dir: Path,
) -> None:
    """
    The endpoint accepts a single certidão negativa document
    without requiring other document types.
    """
    with patch("src.usecases.analysis.celery_app.send_task"):
        response = await client.post(
            "/v1/analyses",
            data={"company_name": "Certidao Only Company"},
            files={
                "certidao_negativa": (
                    "certidao.pdf",
                    certidao_negativa_pdf,
                    "application/pdf",
                )
            },
        )

    assert response.status_code == 202

    job_id = uuid.UUID(response.json()["job_id"])
    stmt = select(models.Document).where(models.Document.job_id == job_id)
    result = await session.exec(stmt)
    documents = result.all()

    assert len(documents) == 1
    assert documents[0].document_type == enums.DocumentType.CERTIDAO_NEGATIVA


# =============================================================================
# GET /v1/analyses/{job_id} - get_document_analysis_job
# =============================================================================


@pytest.mark.asyncio
async def test_get_document_analysis_job_returns_200_with_job_data(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """
    When fetching an existing analysis job by ID,
    the endpoint returns HTTP 200 with job details.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Test Company")
    session.add(analysis_job)
    await session.commit()
    await session.refresh(analysis_job)

    response = await client.get(f"/v1/analyses/{analysis_job.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["id"] == str(analysis_job.id)
    assert data["company_name"] == "Test Company"
    assert data["status"] == enums.AnalysisStatus.PENDING


@pytest.mark.asyncio
async def test_get_document_analysis_job_returns_404_for_nonexistent_job(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """
    When fetching a non-existent analysis job,
    the endpoint returns HTTP 404.
    """
    nonexistent_id = uuid.uuid4()

    response = await client.get(f"/v1/analyses/{nonexistent_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "analysis_job_not_found"
    assert response.json()["error"]["message"] == "Analysis job not found"


@pytest.mark.asyncio
async def test_get_document_analysis_job_includes_documents_in_response(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """
    When fetching an analysis job with documents,
    the response includes document details.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Company With Docs")
    session.add(analysis_job)
    await session.flush()

    document = DocumentFactory.build(
        job_id=analysis_job.id,
        document_type=enums.DocumentType.CONTRATO_SOCIAL,
        filename="contrato.pdf",
        size_bytes=1024,
        checksum_sha256="abc123",
    )
    session.add(document)
    await session.commit()
    await session.refresh(analysis_job)
    await session.refresh(document)

    response = await client.get(f"/v1/analyses/{analysis_job.id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data["documents"]) == 1
    assert data["documents"][0]["id"] == str(document.id)
    assert data["documents"][0]["document_type"] == enums.DocumentType.CONTRATO_SOCIAL
    assert data["documents"][0]["filename"] == "contrato.pdf"
    assert data["documents"][0]["size_bytes"] == 1024


@pytest.mark.asyncio
async def test_get_document_analysis_job_includes_inconsistencies_in_response(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """
    When fetching an analysis job with inconsistencies,
    the response includes inconsistency details.
    """
    analysis_job = AnalysisJobFactory.build(
        company_name="Company With Issues",
        status=enums.AnalysisStatus.SUCCEEDED,
        decision=enums.AnalysisDecision.REPROVADO,
    )
    session.add(analysis_job)
    await session.flush()

    inconsistency = AnalysisInconsistencyFactory.build(
        job_id=analysis_job.id,
        code="cnpj_mismatch",
        severity=enums.InconsistencySeverity.BLOCKER,
        message="CNPJ does not match between documents",
    )
    session.add(inconsistency)
    await session.commit()
    await session.refresh(analysis_job)
    await session.refresh(inconsistency)

    response = await client.get(f"/v1/analyses/{analysis_job.id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data["inconsistencies"]) == 1
    assert data["inconsistencies"][0]["id"] == str(inconsistency.id)
    assert data["inconsistencies"][0]["code"] == "cnpj_mismatch"
    assert data["inconsistencies"][0]["severity"] == enums.InconsistencySeverity.BLOCKER
    assert (
        data["inconsistencies"][0]["message"] == "CNPJ does not match between documents"
    )


@pytest.mark.asyncio
async def test_get_document_analysis_job_returns_succeeded_job_with_decision(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """
    When fetching a succeeded analysis job,
    the response includes the decision field.
    """
    analysis_job = AnalysisJobFactory.build(
        company_name="Approved Company",
        status=enums.AnalysisStatus.SUCCEEDED,
        decision=enums.AnalysisDecision.APROVADO,
    )
    session.add(analysis_job)
    await session.commit()
    await session.refresh(analysis_job)

    response = await client.get(f"/v1/analyses/{analysis_job.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == enums.AnalysisStatus.SUCCEEDED
    assert data["decision"] == enums.AnalysisDecision.APROVADO


@pytest.mark.asyncio
async def test_get_document_analysis_job_returns_failed_job_with_error_details(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """
    When fetching a failed analysis job,
    the response includes error message and details.
    """
    analysis_job = AnalysisJobFactory.build(
        company_name="Failed Company",
        status=enums.AnalysisStatus.FAILED,
        error_message="PDF extraction failed",
        error_details={"error_type": "ExtractionError", "page": 3},
    )
    session.add(analysis_job)
    await session.commit()
    await session.refresh(analysis_job)

    response = await client.get(f"/v1/analyses/{analysis_job.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == enums.AnalysisStatus.FAILED
    assert data["error_message"] == "PDF extraction failed"
    assert data["error_details"]["error_type"] == "ExtractionError"
    assert data["decision"] is None


@pytest.mark.asyncio
async def test_get_document_analysis_job_returns_multiple_documents(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """
    When fetching an analysis job with multiple documents,
    all documents are included in the response.
    """
    analysis_job = AnalysisJobFactory.build(
        company_name="Multi Doc Company",
        status=enums.AnalysisStatus.RUNNING,
    )
    session.add(analysis_job)
    await session.flush()

    documents = [
        DocumentFactory.build(
            job_id=analysis_job.id,
            document_type=enums.DocumentType.CONTRATO_SOCIAL,
            filename="contrato.pdf",
        ),
        DocumentFactory.build(
            job_id=analysis_job.id,
            document_type=enums.DocumentType.CARTAO_CNPJ,
            filename="cnpj.pdf",
        ),
        DocumentFactory.build(
            job_id=analysis_job.id,
            document_type=enums.DocumentType.CERTIDAO_NEGATIVA,
            filename="certidao.pdf",
        ),
    ]
    for doc in documents:
        session.add(doc)
    await session.commit()

    response = await client.get(f"/v1/analyses/{analysis_job.id}")

    assert response.status_code == 200
    data = response.json()
    assert len(data["documents"]) == 3

    doc_types = {doc["document_type"] for doc in data["documents"]}
    assert doc_types == {
        enums.DocumentType.CONTRATO_SOCIAL,
        enums.DocumentType.CARTAO_CNPJ,
        enums.DocumentType.CERTIDAO_NEGATIVA,
    }


@pytest.mark.asyncio
async def test_get_document_analysis_job_returns_empty_lists_when_no_documents_or_inconsistencies(
    client: AsyncClient,
    session: AsyncSession,
) -> None:
    """
    When fetching an analysis job without documents or inconsistencies,
    the response includes empty lists for both.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Empty Job Company")
    session.add(analysis_job)
    await session.commit()
    await session.refresh(analysis_job)

    response = await client.get(f"/v1/analyses/{analysis_job.id}")

    assert response.status_code == 200
    data = response.json()
    assert data["documents"] == []
    assert data["inconsistencies"] == []
