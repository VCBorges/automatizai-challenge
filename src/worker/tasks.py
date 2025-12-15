from __future__ import annotations

import asyncio
import uuid
from typing import Any

from src import usecases
from src.core.database.core import SessionFactory
from src.worker.celery import celery_app


@celery_app.task(name="src.worker.tasks.ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


@celery_app.task(name="src.worker.tasks.analyze_documents_job")
def analyze_documents_job(
    *,
    job_id: str,
    correlation_id: str,
) -> dict[str, Any]:
    async def run_async_task(job_id: uuid.UUID) -> dict[str, Any]:
        async with SessionFactory() as session:
            return await usecases.AnalyzeDocuments(
                session=session,
                job_id=job_id,
                correlation_id=correlation_id,
            ).handle()

    return asyncio.run(run_async_task(uuid.UUID(job_id)))
