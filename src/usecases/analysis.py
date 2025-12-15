import logging
import uuid

from fastapi import UploadFile
from sqlalchemy.orm import selectinload
from sqlmodel import select

from src import agents, enums, models
from src.core.base.exceptions import ApplicationError
from src.core.base.usecases import UseCase
from src.core.storage import get_storage
from src.core.storage.backends import LocalFileStorage
from src.core.types import DictStrAny
from src.core.utils.datetime import now
from src.exceptions import AnalysisJobNotFoundError
from src.schemas import AnalysisCreateInput
from src.services.pdf import extract_text_from_pdf
from src.worker.celery import celery_app

logger = logging.getLogger(__name__)


class CreateDocumentAnalysisJob(UseCase):
    """
    Create an AnalysisJob from uploaded PDF documents.

    - Create AnalysisJob + Document rows
    - Persist uploaded PDFs into storage (object_key)
    - Enqueue Celery task to process the job
    """

    data: AnalysisCreateInput

    async def handle(self) -> DictStrAny:
        logger.info(
            "Creating new document analysis job",
            extra={"company_name": self.data.company_name},
        )

        analysis_job = await self._create_analysis_job()

        logger.info(
            "Analysis job created",
            extra={
                "job_id": str(analysis_job.id),
                "company_name": self.data.company_name,
            },
        )

        await self._process_documents(analysis_job)
        await self.session.commit()
        self._enqueue_analysis_task(analysis_job)

        logger.info(
            "Analysis job submitted for processing",
            extra={
                "job_id": str(analysis_job.id),
                "status": analysis_job.status.value,
            },
        )

        return {
            "job_id": analysis_job.id,
            "status": analysis_job.status,
        }

    async def _create_analysis_job(self) -> models.AnalysisJob:
        """Create and persist the AnalysisJob record."""
        analysis_job = models.AnalysisJob(
            company_name=self.data.company_name,
            status=enums.AnalysisStatus.PENDING,
        )
        self.session.add(analysis_job)
        await self.session.flush()
        return analysis_job

    def _get_document_mapping(
        self,
    ) -> list[tuple[enums.DocumentType, UploadFile | None]]:
        """Map form fields to their corresponding document types."""
        return [
            (enums.DocumentType.CONTRATO_SOCIAL, self.data.contrato_social),
            (enums.DocumentType.CARTAO_CNPJ, self.data.cartao_cnpj),
            (enums.DocumentType.CERTIDAO_NEGATIVA, self.data.certidao_negativa),
        ]

    async def _process_documents(self, analysis_job: models.AnalysisJob) -> None:
        """Process and persist each uploaded document."""
        storage = get_storage()

        for document_type, upload_file in self._get_document_mapping():
            if upload_file is None:
                continue

            document = await self._store_and_create_document(
                storage=storage,
                analysis_job=analysis_job,
                document_type=document_type,
                upload_file=upload_file,
            )
            self.session.add(document)

    async def _store_and_create_document(
        self,
        storage,
        analysis_job: models.AnalysisJob,
        document_type: enums.DocumentType,
        upload_file: UploadFile,
    ) -> models.Document:
        """Store file in storage and create Document record."""
        object_key = f"{analysis_job.id}/{document_type.value}/{upload_file.filename}"

        content = await upload_file.read()
        stored_info = await storage.save(content=content, object_key=object_key)

        logger.info(
            "Document stored successfully",
            extra={
                "job_id": str(analysis_job.id),
                "document_type": document_type.value,
                "document_filename": upload_file.filename,
                "size_bytes": stored_info.size_bytes,
                "object_key": stored_info.object_key,
            },
        )

        return models.Document(
            job_id=analysis_job.id,
            document_type=document_type,
            filename=upload_file.filename or "unknown.pdf",
            content_type=upload_file.content_type or "application/pdf",
            size_bytes=stored_info.size_bytes,
            checksum_sha256=stored_info.checksum_sha256,
            object_key=stored_info.object_key,
        )

    def _enqueue_analysis_task(self, analysis_job: models.AnalysisJob) -> None:
        """Enqueue the Celery task to process the analysis job."""
        celery_app.send_task(
            "src.worker.tasks.analyze_documents_job",
            kwargs={
                "job_id": str(analysis_job.id),
                "correlation_id": self.correlation_id,
            },
        )


class GetDocumentAnalysisJob(UseCase):
    """
    Fetch AnalysisJob by id (including documents + inconsistencies)
    and return serialized output for the API.
    """

    job_id: uuid.UUID

    async def handle(self) -> DictStrAny:
        stmt = (
            select(models.AnalysisJob)
            .where(models.AnalysisJob.id == self.job_id)
            .options(
                selectinload(models.AnalysisJob.documents),
                selectinload(models.AnalysisJob.inconsistencies),
            )
        )
        result = await self.session.exec(stmt)
        analysis_job = result.one_or_none()

        if not analysis_job:
            logger.warning(
                "Analysis job not found",
                extra={"job_id": str(self.job_id)},
            )
            raise AnalysisJobNotFoundError(job_id=str(self.job_id))

        return {
            "id": analysis_job.id,
            "company_name": analysis_job.company_name,
            "status": analysis_job.status,
            "decision": analysis_job.decision,
            "error_message": analysis_job.error_message,
            "error_details": analysis_job.error_details,
            "finished_at": analysis_job.finished_at,
            "created_at": analysis_job.created_at,
            "updated_at": analysis_job.updated_at,
            "documents": [
                {
                    "id": doc.id,
                    "document_type": doc.document_type,
                    "filename": doc.filename,
                    "content_type": doc.content_type,
                    "size_bytes": doc.size_bytes,
                    "checksum_sha256": doc.checksum_sha256,
                    "object_key": doc.object_key,
                    "extracted_text": doc.extracted_text,
                    "extracted_data": doc.extracted_data,
                    "llm_model": doc.llm_model,
                    "created_at": doc.created_at,
                    "updated_at": doc.updated_at,
                }
                for doc in analysis_job.documents
            ],
            "inconsistencies": [
                {
                    "id": inc.id,
                    "code": inc.code,
                    "severity": inc.severity,
                    "message": inc.message,
                    "pointers": inc.pointers,
                    "document_id": inc.document_id,
                }
                for inc in analysis_job.inconsistencies
            ],
        }


class AnalyzeDocuments(UseCase):
    """
    Worker-side usecase that processes an analysis job:
    - Load job + documents from DB
    - Extract text from PDFs
    - Run LangGraph agents for structured extraction
    - Run cross-document validation
    - Persist decision and inconsistencies
    """

    job_id: uuid.UUID

    async def handle(self) -> DictStrAny:
        logger.info(
            "Starting document analysis job",
            extra={"job_id": str(self.job_id)},
        )

        analysis_job = await self._load_analysis_job()

        try:
            await self._mark_job_running(analysis_job)
            extraction_results = await self._process_all_documents(analysis_job)
            analysis_result = await self._run_cross_document_analysis(
                analysis_job, extraction_results
            )
            self._persist_inconsistencies(
                analysis_job, analysis_result, extraction_results
            )
            return await self._mark_job_succeeded(analysis_job, analysis_result)

        except Exception as e:
            return await self._mark_job_failed(analysis_job, e)

    async def _load_analysis_job(self) -> models.AnalysisJob:
        stmt = (
            select(models.AnalysisJob)
            .where(models.AnalysisJob.id == self.job_id)
            .options(selectinload(models.AnalysisJob.documents))
        )
        result = await self.session.exec(stmt)
        analysis_job = result.one_or_none()

        if not analysis_job:
            logger.error(
                "Analysis job not found for processing",
                extra={"job_id": str(self.job_id)},
            )
            raise AnalysisJobNotFoundError(job_id=str(self.job_id))

        return analysis_job

    async def _mark_job_running(self, analysis_job: models.AnalysisJob) -> None:
        analysis_job.status = enums.AnalysisStatus.RUNNING
        analysis_job.updated_at = now()
        await self.session.commit()

        logger.info(
            "Analysis job status updated to RUNNING",
            extra={
                "job_id": str(analysis_job.id),
                "company_name": analysis_job.company_name,
                "document_count": len(analysis_job.documents),
            },
        )

    def _get_file_path(self, document: models.Document) -> str:
        storage = get_storage()

        if isinstance(storage, LocalFileStorage):
            return str(storage.get_absolute_path(document.object_key))

        raise NotImplementedError(
            "Non-local storage not yet supported for PDF extraction"
        )

    async def _extract_document_data(
        self,
        document: models.Document,
        extracted_text: str,
    ) -> DictStrAny | None:
        extraction_result = None

        if document.document_type == enums.DocumentType.CONTRATO_SOCIAL:
            extraction_result = await agents.extract_contrato_social(
                extracted_text=extracted_text,
                correlation_id=self.correlation_id,
            )

        elif document.document_type == enums.DocumentType.CARTAO_CNPJ:
            extraction_result = await agents.extract_cartao_cnpj(
                extracted_text=extracted_text,
                correlation_id=self.correlation_id,
            )

        elif document.document_type == enums.DocumentType.CERTIDAO_NEGATIVA:
            extraction_result = await agents.extract_certidao_negativa_federal(
                extracted_text=extracted_text,
                correlation_id=self.correlation_id,
            )

        if extraction_result:
            document.extracted_data = extraction_result.data.model_dump(mode="json")

        return extraction_result

    async def _process_document(
        self,
        analysis_job: models.AnalysisJob,
        document: models.Document,
    ) -> DictStrAny | None:
        logger.info(
            "Processing document",
            extra={
                "job_id": str(analysis_job.id),
                "document_id": str(document.id),
                "document_type": document.document_type.value,
                "document_filename": document.filename,
            },
        )

        file_path = self._get_file_path(document)
        extracted_text = extract_text_from_pdf(file_path)
        document.extracted_text = extracted_text

        logger.debug(
            "PDF text extracted",
            extra={
                "job_id": str(analysis_job.id),
                "document_id": str(document.id),
                "document_type": document.document_type.value,
                "extracted_text_length": len(extracted_text),
            },
        )

        extraction_result = await self._extract_document_data(document, extracted_text)
        document.updated_at = now()

        logger.info(
            "Document extraction completed",
            extra={
                "job_id": str(analysis_job.id),
                "document_id": str(document.id),
                "document_type": document.document_type.value,
            },
        )

        return extraction_result

    async def _process_all_documents(
        self,
        analysis_job: models.AnalysisJob,
    ) -> dict[enums.DocumentType, DictStrAny]:
        extraction_results: dict[enums.DocumentType, DictStrAny] = {}

        for document in analysis_job.documents:
            extraction_result = await self._process_document(analysis_job, document)

            if extraction_result:
                extraction_results[document.document_type] = {
                    "result": extraction_result,
                    "document": document,
                }

        return extraction_results

    async def _run_cross_document_analysis(
        self,
        analysis_job: models.AnalysisJob,
        extraction_results: dict[enums.DocumentType, DictStrAny],
    ) -> agents.CrossDocumentAnalysisResult:
        logger.info(
            "Starting cross-document analysis",
            extra={
                "job_id": str(analysis_job.id),
                "documents_extracted": list(extraction_results.keys()),
            },
        )

        contrato_result = extraction_results.get(enums.DocumentType.CONTRATO_SOCIAL)
        cartao_result = extraction_results.get(enums.DocumentType.CARTAO_CNPJ)
        certidao_result = extraction_results.get(enums.DocumentType.CERTIDAO_NEGATIVA)

        analysis_result = await agents.analyze_documents(
            contrato_social=contrato_result["result"] if contrato_result else None,
            cartao_cnpj=cartao_result["result"] if cartao_result else None,
            certidao_negativa=certidao_result["result"] if certidao_result else None,
            correlation_id=self.correlation_id,
        )

        logger.info(
            "Cross-document analysis completed",
            extra={
                "job_id": str(analysis_job.id),
                "decision": analysis_result.decision.value,
                "inconsistencies_count": len(analysis_result.inconsistencies),
            },
        )

        return analysis_result

    def _persist_inconsistencies(
        self,
        analysis_job: models.AnalysisJob,
        analysis_result: agents.CrossDocumentAnalysisResult,
        extraction_results: dict[enums.DocumentType, DictStrAny],
    ) -> None:
        for inc in analysis_result.inconsistencies:
            document_id = None
            if inc.documents:
                doc_type_str = inc.documents[0]
                for doc_type, data in extraction_results.items():
                    if doc_type.value == doc_type_str:
                        document_id = data["document"].id
                        break

            inconsistency = models.AnalysisInconsistency(
                job_id=analysis_job.id,
                document_id=document_id,
                code=inc.code,
                severity=inc.severity,
                message=inc.message,
                pointers={
                    "field": inc.field,
                    "documents": inc.documents,
                    "values": inc.values,
                },
            )
            self.session.add(inconsistency)

            logger.info(
                "Inconsistency detected",
                extra={
                    "job_id": str(analysis_job.id),
                    "inconsistency_code": inc.code,
                    "severity": inc.severity.value,
                    "field": inc.field,
                    "documents": inc.documents,
                },
            )

    async def _mark_job_succeeded(
        self,
        analysis_job: models.AnalysisJob,
        analysis_result: agents.CrossDocumentAnalysisResult,
    ) -> DictStrAny:
        analysis_job.decision = analysis_result.decision
        analysis_job.status = enums.AnalysisStatus.SUCCEEDED
        analysis_job.finished_at = now()
        analysis_job.updated_at = now()

        await self.session.commit()

        logger.info(
            "Analysis job completed successfully",
            extra={
                "job_id": str(analysis_job.id),
                "company_name": analysis_job.company_name,
                "status": analysis_job.status.value,
                "decision": analysis_job.decision.value,
                "inconsistencies_count": len(analysis_result.inconsistencies),
            },
        )

        return {
            "job_id": str(analysis_job.id),
            "status": analysis_job.status.value,
            "decision": analysis_job.decision.value if analysis_job.decision else None,
        }

    async def _mark_job_failed(
        self,
        analysis_job: models.AnalysisJob,
        error: Exception,
    ) -> DictStrAny:
        error_code = (
            error.code if isinstance(error, ApplicationError) else type(error).__name__
        )
        error_details = error.details if isinstance(error, ApplicationError) else {}

        logger.exception(
            "Analysis job failed",
            extra={
                "job_id": str(self.job_id),
                "company_name": analysis_job.company_name,
                "error_type": type(error).__name__,
                "error_code": error_code,
                "error_message": str(error),
            },
        )

        analysis_job.status = enums.AnalysisStatus.FAILED
        analysis_job.error_message = str(error)
        analysis_job.error_details = {
            "error_type": type(error).__name__,
            "error_code": error_code,
            **error_details,
        }
        analysis_job.finished_at = now()
        analysis_job.updated_at = now()

        await self.session.commit()

        return {
            "job_id": str(analysis_job.id),
            "status": analysis_job.status.value,
            "error": str(error),
        }
