import typing as tp
import uuid

from asgi_correlation_id import correlation_id
from fastapi import APIRouter, Form

from src import schemas, usecases
from src.api.dependencies import SessionDep

router = APIRouter(
    prefix="/v1",
    tags=["v1"],
)


@router.get("/health")
async def health():
    return {"status": "ok"}


@router.post(
    "/analyses",
    response_model=schemas.AnalysisCreateResponse,
    status_code=202,
)
async def create_document_analysis_job(
    session: SessionDep,
    data: tp.Annotated[
        schemas.AnalysisCreateInput,
        Form(media_type="multipart/form-data"),
    ],
):
    return await usecases.CreateDocumentAnalysisJob(
        session=session,
        data=data,
        correlation_id=correlation_id.get(),
    ).handle()


@router.get(
    "/analyses/{job_id}",
    response_model=schemas.AnalysisJobOut,
)
async def get_document_analysis_job(
    session: SessionDep,
    job_id: uuid.UUID,
):
    return await usecases.GetDocumentAnalysisJob(
        session=session,
        job_id=job_id,
        correlation_id=correlation_id.get(),
    ).handle()
