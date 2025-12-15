from asgi_correlation_id.extensions.celery import load_correlation_ids
from celery import Celery

from src.core.settings import get_settings

load_correlation_ids()

settings = get_settings()

celery_app = Celery(
    main="app",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=[
        "src.worker.tasks",
    ],
)


celery_app.conf.worker_hijack_root_logger = False

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)
