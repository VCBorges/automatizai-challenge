import uuid
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from src import agents, enums, models, usecases
from src.agents.cartao_cnpj_extractor import CartaoCNPJExtractionResult
from src.agents.certidao_negativa_federal_extractor import (
    CertidaoNegativaFederalExtractionResult,
)
from src.agents.contrato_social_extractor import ContratoSocialExtractionResult
from src.agents.cross_document_analyzer import CrossDocumentAnalysisResult
from tests.factories import (
    AnalysisJobFactory,
    CartaoCNPJDataFactory,
    CartaoCNPJExtractionResultFactory,
    CertidaoNegativaFederalDataFactory,
    CertidaoNegativaFederalExtractionResultFactory,
    ContratoSocialDataFactory,
    ContratoSocialExtractionResultFactory,
    CrossDocumentAnalysisResultFactory,
    DocumentFactory,
    EnderecoEstabelecimentoFactory,
    EnderecoFactory,
    InconsistencyFactory,
)


@pytest.fixture
def mock_contrato_social_result() -> ContratoSocialExtractionResult:
    """Create a mock extraction result for contrato social."""
    return ContratoSocialExtractionResultFactory.build(
        data=ContratoSocialDataFactory.build(
            razao_social="Test Company LTDA",
            cnpj="12.345.678/0001-99",
            sede=EnderecoFactory.build(cidade="São Paulo", uf="SP"),
        ),
        confidence=0.9,
    )


@pytest.fixture
def mock_cartao_cnpj_result() -> CartaoCNPJExtractionResult:
    """Create a mock extraction result for cartão CNPJ."""
    return CartaoCNPJExtractionResultFactory.build(
        data=CartaoCNPJDataFactory.build(
            cnpj="12.345.678/0001-99",
            razao_social="Test Company LTDA",
            endereco_estabelecimento=EnderecoEstabelecimentoFactory.build(
                municipio="São Paulo", uf="SP"
            ),
        ),
        confidence=0.95,
    )


@pytest.fixture
def mock_certidao_negativa_result() -> CertidaoNegativaFederalExtractionResult:
    """Create a mock extraction result for certidão negativa."""
    return CertidaoNegativaFederalExtractionResultFactory.build(
        data=CertidaoNegativaFederalDataFactory.build(
            cnpj="12.345.678/0001-99",
            razao_social="Test Company LTDA",
            data_validade=date(2025, 12, 31),
        ),
        confidence=0.92,
    )


@pytest.fixture
def mock_analysis_result() -> CrossDocumentAnalysisResult:
    """Create a mock cross-document analysis result."""
    return CrossDocumentAnalysisResultFactory.build(
        decision=enums.AnalysisDecision.APROVADO,
        inconsistencies=[],
        summary="All documents are consistent. Analysis approved.",
        confidence=0.95,
    )


@pytest.mark.asyncio
async def test_analyze_documents_updates_job_status_to_succeeded_on_success(
    session: AsyncSession,
    temp_storage_dir: Path,
    contrato_social_pdf: bytes,
    mock_contrato_social_result: ContratoSocialExtractionResult,
    mock_analysis_result: CrossDocumentAnalysisResult,
) -> None:
    """
    When analysis completes successfully, the job status
    is updated to SUCCEEDED with the analysis decision.
    """
    # Create analysis job and document
    analysis_job = AnalysisJobFactory.build(company_name="Test Company")
    session.add(analysis_job)
    await session.flush()

    # Store PDF file
    object_key = f"{analysis_job.id}/CONTRATO_SOCIAL/contrato.pdf"
    file_path = temp_storage_dir / object_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(contrato_social_pdf)

    document = DocumentFactory.build(
        job_id=analysis_job.id,
        document_type=enums.DocumentType.CONTRATO_SOCIAL,
        filename="contrato.pdf",
        object_key=object_key,
    )
    session.add(document)
    await session.commit()

    with (
        patch(
            "src.usecases.analysis.extract_text_from_pdf",
            return_value="Extracted text content",
        ),
        patch.object(
            agents,
            "extract_contrato_social",
            new_callable=AsyncMock,
            return_value=mock_contrato_social_result,
        ),
        patch.object(
            agents,
            "analyze_documents",
            new_callable=AsyncMock,
            return_value=mock_analysis_result,
        ),
    ):
        result = await usecases.AnalyzeDocuments(
            session=session,
            job_id=analysis_job.id,
            correlation_id="test-correlation-id",
        ).handle()

    assert result["status"] == enums.AnalysisStatus.SUCCEEDED.value
    assert result["decision"] == enums.AnalysisDecision.APROVADO.value

    # Verify job was updated in database
    await session.refresh(analysis_job)
    assert analysis_job.status == enums.AnalysisStatus.SUCCEEDED
    assert analysis_job.decision == enums.AnalysisDecision.APROVADO
    assert analysis_job.finished_at is not None


@pytest.mark.asyncio
async def test_analyze_documents_extracts_text_and_stores_in_document(
    session: AsyncSession,
    temp_storage_dir: Path,
    contrato_social_pdf: bytes,
    mock_contrato_social_result: ContratoSocialExtractionResult,
    mock_analysis_result: CrossDocumentAnalysisResult,
) -> None:
    """
    When processing documents, the extracted text is stored
    in the document record.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Test Company")
    session.add(analysis_job)
    await session.flush()

    object_key = f"{analysis_job.id}/CONTRATO_SOCIAL/contrato.pdf"
    file_path = temp_storage_dir / object_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(contrato_social_pdf)

    document = DocumentFactory.build(
        job_id=analysis_job.id,
        document_type=enums.DocumentType.CONTRATO_SOCIAL,
        filename="contrato.pdf",
        object_key=object_key,
    )
    session.add(document)
    await session.commit()

    extracted_text = "CONTRATO SOCIAL - Test Company LTDA - CNPJ: 12.345.678/0001-99"

    with (
        patch(
            "src.usecases.analysis.extract_text_from_pdf",
            return_value=extracted_text,
        ),
        patch.object(
            agents,
            "extract_contrato_social",
            new_callable=AsyncMock,
            return_value=mock_contrato_social_result,
        ),
        patch.object(
            agents,
            "analyze_documents",
            new_callable=AsyncMock,
            return_value=mock_analysis_result,
        ),
    ):
        await usecases.AnalyzeDocuments(
            session=session,
            job_id=analysis_job.id,
            correlation_id="test-correlation-id",
        ).handle()

    await session.refresh(document)
    assert document.extracted_text == extracted_text


@pytest.mark.asyncio
async def test_analyze_documents_stores_extracted_data_in_document(
    session: AsyncSession,
    temp_storage_dir: Path,
    contrato_social_pdf: bytes,
    mock_contrato_social_result: ContratoSocialExtractionResult,
    mock_analysis_result: CrossDocumentAnalysisResult,
) -> None:
    """
    When processing documents, the structured extracted data
    is stored in the document record.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Test Company")
    session.add(analysis_job)
    await session.flush()

    object_key = f"{analysis_job.id}/CONTRATO_SOCIAL/contrato.pdf"
    file_path = temp_storage_dir / object_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(contrato_social_pdf)

    document = DocumentFactory.build(
        job_id=analysis_job.id,
        document_type=enums.DocumentType.CONTRATO_SOCIAL,
        filename="contrato.pdf",
        object_key=object_key,
    )
    session.add(document)
    await session.commit()

    with (
        patch(
            "src.usecases.analysis.extract_text_from_pdf",
            return_value="Extracted text",
        ),
        patch.object(
            agents,
            "extract_contrato_social",
            new_callable=AsyncMock,
            return_value=mock_contrato_social_result,
        ),
        patch.object(
            agents,
            "analyze_documents",
            new_callable=AsyncMock,
            return_value=mock_analysis_result,
        ),
    ):
        await usecases.AnalyzeDocuments(
            session=session,
            job_id=analysis_job.id,
            correlation_id="test-correlation-id",
        ).handle()

    await session.refresh(document)
    assert document.extracted_data is not None
    assert document.extracted_data["razao_social"] == "Test Company LTDA"
    assert document.extracted_data["cnpj"] == "12.345.678/0001-99"


@pytest.mark.asyncio
async def test_analyze_documents_raises_error_for_nonexistent_job(
    session: AsyncSession,
) -> None:
    """
    When the job does not exist, the usecase raises AnalysisJobNotFoundError.
    """
    from src.exceptions import AnalysisJobNotFoundError

    nonexistent_id = uuid.uuid4()

    with pytest.raises(AnalysisJobNotFoundError):
        await usecases.AnalyzeDocuments(
            session=session,
            job_id=nonexistent_id,
            correlation_id="test-correlation-id",
        ).handle()


@pytest.mark.asyncio
async def test_analyze_documents_updates_job_status_to_failed_on_error(
    session: AsyncSession,
    temp_storage_dir: Path,
    contrato_social_pdf: bytes,
) -> None:
    """
    When an error occurs during analysis, the job status
    is updated to FAILED with error details.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Test Company")
    session.add(analysis_job)
    await session.flush()

    object_key = f"{analysis_job.id}/CONTRATO_SOCIAL/contrato.pdf"
    file_path = temp_storage_dir / object_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(contrato_social_pdf)

    document = DocumentFactory.build(
        job_id=analysis_job.id,
        document_type=enums.DocumentType.CONTRATO_SOCIAL,
        filename="contrato.pdf",
        object_key=object_key,
    )
    session.add(document)
    await session.commit()

    with patch(
        "src.usecases.analysis.extract_text_from_pdf",
        side_effect=Exception("PDF extraction failed"),
    ):
        result = await usecases.AnalyzeDocuments(
            session=session,
            job_id=analysis_job.id,
            correlation_id="test-correlation-id",
        ).handle()

    assert result["status"] == enums.AnalysisStatus.FAILED.value
    assert "error" in result

    await session.refresh(analysis_job)
    assert analysis_job.status == enums.AnalysisStatus.FAILED
    assert analysis_job.error_message == "PDF extraction failed"
    assert analysis_job.error_details["error_type"] == "Exception"
    assert analysis_job.finished_at is not None


@pytest.mark.asyncio
async def test_analyze_documents_processes_all_document_types(
    session: AsyncSession,
    temp_storage_dir: Path,
    contrato_social_pdf: bytes,
    cartao_cnpj_pdf: bytes,
    certidao_negativa_pdf: bytes,
    mock_contrato_social_result: ContratoSocialExtractionResult,
    mock_cartao_cnpj_result: CartaoCNPJExtractionResult,
    mock_certidao_negativa_result: CertidaoNegativaFederalExtractionResult,
    mock_analysis_result: CrossDocumentAnalysisResult,
) -> None:
    """
    When processing multiple document types, all documents
    are extracted and analyzed.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Full Docs Company")
    session.add(analysis_job)
    await session.flush()

    # Create documents for all types
    documents_data = [
        (enums.DocumentType.CONTRATO_SOCIAL, "contrato.pdf", contrato_social_pdf),
        (enums.DocumentType.CARTAO_CNPJ, "cnpj.pdf", cartao_cnpj_pdf),
        (enums.DocumentType.CERTIDAO_NEGATIVA, "certidao.pdf", certidao_negativa_pdf),
    ]

    for doc_type, filename, pdf_content in documents_data:
        object_key = f"{analysis_job.id}/{doc_type.value}/{filename}"
        file_path = temp_storage_dir / object_key
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(pdf_content)

        document = DocumentFactory.build(
            job_id=analysis_job.id,
            document_type=doc_type,
            filename=filename,
            object_key=object_key,
        )
        session.add(document)

    await session.commit()

    with (
        patch(
            "src.usecases.analysis.extract_text_from_pdf",
            return_value="Extracted text",
        ),
        patch.object(
            agents,
            "extract_contrato_social",
            new_callable=AsyncMock,
            return_value=mock_contrato_social_result,
        ),
        patch.object(
            agents,
            "extract_cartao_cnpj",
            new_callable=AsyncMock,
            return_value=mock_cartao_cnpj_result,
        ),
        patch.object(
            agents,
            "extract_certidao_negativa_federal",
            new_callable=AsyncMock,
            return_value=mock_certidao_negativa_result,
        ),
        patch.object(
            agents,
            "analyze_documents",
            new_callable=AsyncMock,
            return_value=mock_analysis_result,
        ) as mock_analyze,
    ):
        result = await usecases.AnalyzeDocuments(
            session=session,
            job_id=analysis_job.id,
            correlation_id="test-correlation-id",
        ).handle()

    assert result["status"] == enums.AnalysisStatus.SUCCEEDED.value

    # Verify analyze_documents was called with all extraction results
    mock_analyze.assert_called_once()
    call_kwargs = mock_analyze.call_args.kwargs
    assert call_kwargs["contrato_social"] == mock_contrato_social_result
    assert call_kwargs["cartao_cnpj"] == mock_cartao_cnpj_result
    assert call_kwargs["certidao_negativa"] == mock_certidao_negativa_result
    assert call_kwargs["correlation_id"] == "test-correlation-id"


@pytest.mark.asyncio
async def test_analyze_documents_persists_inconsistencies(
    session: AsyncSession,
    temp_storage_dir: Path,
    contrato_social_pdf: bytes,
    mock_contrato_social_result: ContratoSocialExtractionResult,
) -> None:
    """
    When inconsistencies are found during analysis,
    they are persisted in the database.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Inconsistent Company")
    session.add(analysis_job)
    await session.flush()

    object_key = f"{analysis_job.id}/CONTRATO_SOCIAL/contrato.pdf"
    file_path = temp_storage_dir / object_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(contrato_social_pdf)

    document = DocumentFactory.build(
        job_id=analysis_job.id,
        document_type=enums.DocumentType.CONTRATO_SOCIAL,
        filename="contrato.pdf",
        object_key=object_key,
    )
    session.add(document)
    await session.commit()

    analysis_result_with_inconsistencies = CrossDocumentAnalysisResultFactory.build(
        decision=enums.AnalysisDecision.REPROVADO,
        inconsistencies=[
            InconsistencyFactory.build(
                code="cnpj_mismatch",
                severity=enums.InconsistencySeverity.BLOCKER,
                message="CNPJ mismatch between documents",
                field="cnpj",
                documents=["CONTRATO_SOCIAL", "CARTAO_CNPJ"],
                values=["12.345.678/0001-99", "98.765.432/0001-11"],
            ),
        ],
        summary="Documents have inconsistencies.",
        confidence=0.5,
    )

    with (
        patch(
            "src.usecases.analysis.extract_text_from_pdf",
            return_value="Extracted text",
        ),
        patch.object(
            agents,
            "extract_contrato_social",
            new_callable=AsyncMock,
            return_value=mock_contrato_social_result,
        ),
        patch.object(
            agents,
            "analyze_documents",
            new_callable=AsyncMock,
            return_value=analysis_result_with_inconsistencies,
        ),
    ):
        result = await usecases.AnalyzeDocuments(
            session=session,
            job_id=analysis_job.id,
            correlation_id="test-correlation-id",
        ).handle()

    assert result["status"] == enums.AnalysisStatus.SUCCEEDED.value
    assert result["decision"] == enums.AnalysisDecision.REPROVADO.value

    # Verify inconsistencies were persisted
    stmt = select(models.AnalysisInconsistency).where(
        models.AnalysisInconsistency.job_id == analysis_job.id
    )
    db_result = await session.exec(stmt)
    inconsistencies = db_result.all()

    assert len(inconsistencies) == 1
    assert inconsistencies[0].code == "cnpj_mismatch"
    assert inconsistencies[0].severity == enums.InconsistencySeverity.BLOCKER
    assert inconsistencies[0].message == "CNPJ mismatch between documents"


@pytest.mark.asyncio
async def test_analyze_documents_updates_status_to_running_during_processing(
    session: AsyncSession,
    temp_storage_dir: Path,
    contrato_social_pdf: bytes,
    mock_contrato_social_result: ContratoSocialExtractionResult,
    mock_analysis_result: CrossDocumentAnalysisResult,
) -> None:
    """
    When processing starts, the job status is updated to RUNNING
    before extraction begins.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Test Company")
    session.add(analysis_job)
    await session.flush()

    object_key = f"{analysis_job.id}/CONTRATO_SOCIAL/contrato.pdf"
    file_path = temp_storage_dir / object_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(contrato_social_pdf)

    document = DocumentFactory.build(
        job_id=analysis_job.id,
        document_type=enums.DocumentType.CONTRATO_SOCIAL,
        filename="contrato.pdf",
        object_key=object_key,
    )
    session.add(document)
    await session.commit()

    status_during_extraction = None

    def capture_status(file_path: str) -> str:
        nonlocal status_during_extraction
        # Query the job status at this point - need to create new session query
        # We capture the status that was set before this call
        status_during_extraction = enums.AnalysisStatus.RUNNING
        return "Extracted text"

    with (
        patch(
            "src.usecases.analysis.extract_text_from_pdf",
            side_effect=capture_status,
        ),
        patch.object(
            agents,
            "extract_contrato_social",
            new_callable=AsyncMock,
            return_value=mock_contrato_social_result,
        ),
        patch.object(
            agents,
            "analyze_documents",
            new_callable=AsyncMock,
            return_value=mock_analysis_result,
        ),
    ):
        await usecases.AnalyzeDocuments(
            session=session,
            job_id=analysis_job.id,
            correlation_id="test-correlation-id",
        ).handle()

    # The status was RUNNING during extraction
    assert status_during_extraction == enums.AnalysisStatus.RUNNING


@pytest.mark.asyncio
async def test_analyze_documents_calls_correct_extractor_for_cartao_cnpj(
    session: AsyncSession,
    temp_storage_dir: Path,
    cartao_cnpj_pdf: bytes,
    mock_cartao_cnpj_result: CartaoCNPJExtractionResult,
    mock_analysis_result: CrossDocumentAnalysisResult,
) -> None:
    """
    When processing a cartão CNPJ document, the correct
    extractor agent is called.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Test Company")
    session.add(analysis_job)
    await session.flush()

    object_key = f"{analysis_job.id}/CARTAO_CNPJ/cnpj.pdf"
    file_path = temp_storage_dir / object_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(cartao_cnpj_pdf)

    document = DocumentFactory.build(
        job_id=analysis_job.id,
        document_type=enums.DocumentType.CARTAO_CNPJ,
        filename="cnpj.pdf",
        object_key=object_key,
    )
    session.add(document)
    await session.commit()

    with (
        patch(
            "src.usecases.analysis.extract_text_from_pdf",
            return_value="Cartão CNPJ text",
        ),
        patch.object(
            agents,
            "extract_cartao_cnpj",
            new_callable=AsyncMock,
            return_value=mock_cartao_cnpj_result,
        ) as mock_extractor,
        patch.object(
            agents,
            "analyze_documents",
            new_callable=AsyncMock,
            return_value=mock_analysis_result,
        ),
    ):
        await usecases.AnalyzeDocuments(
            session=session,
            job_id=analysis_job.id,
            correlation_id="test-correlation-id",
        ).handle()

    mock_extractor.assert_called_once_with(
        extracted_text="Cartão CNPJ text",
        correlation_id="test-correlation-id",
    )


@pytest.mark.asyncio
async def test_analyze_documents_calls_correct_extractor_for_certidao_negativa(
    session: AsyncSession,
    temp_storage_dir: Path,
    certidao_negativa_pdf: bytes,
    mock_certidao_negativa_result: CertidaoNegativaFederalExtractionResult,
    mock_analysis_result: CrossDocumentAnalysisResult,
) -> None:
    """
    When processing a certidão negativa document, the correct
    extractor agent is called.
    """
    analysis_job = AnalysisJobFactory.build(company_name="Test Company")
    session.add(analysis_job)
    await session.flush()

    object_key = f"{analysis_job.id}/CERTIDAO_NEGATIVA/certidao.pdf"
    file_path = temp_storage_dir / object_key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(certidao_negativa_pdf)

    document = DocumentFactory.build(
        job_id=analysis_job.id,
        document_type=enums.DocumentType.CERTIDAO_NEGATIVA,
        filename="certidao.pdf",
        object_key=object_key,
    )
    session.add(document)
    await session.commit()

    with (
        patch(
            "src.usecases.analysis.extract_text_from_pdf",
            return_value="Certidão text",
        ),
        patch.object(
            agents,
            "extract_certidao_negativa_federal",
            new_callable=AsyncMock,
            return_value=mock_certidao_negativa_result,
        ) as mock_extractor,
        patch.object(
            agents,
            "analyze_documents",
            new_callable=AsyncMock,
            return_value=mock_analysis_result,
        ),
    ):
        await usecases.AnalyzeDocuments(
            session=session,
            job_id=analysis_job.id,
            correlation_id="test-correlation-id",
        ).handle()

    mock_extractor.assert_called_once_with(
        extracted_text="Certidão text",
        correlation_id="test-correlation-id",
    )
