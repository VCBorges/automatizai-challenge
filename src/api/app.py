import logging
import logging.config
import typing as tp
from contextlib import asynccontextmanager

from asgi_correlation_id import CorrelationIdMiddleware
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlmodel import SQLModel

from src.api.v1.routes import router as v1_router
from src.core.base.exceptions import (
    ApplicationError,
    ExternalServiceError,
    ProcessingError,
    ResourceNotFoundError,
    ValidationError,
)
from src.core.database.core import engine
from src.core.logging.config import LOGGING_CONFIG
from src.core.settings import get_settings

logging.config.dictConfig(LOGGING_CONFIG)

logger = logging.getLogger(__name__)
settings = get_settings()


def include_routes(app: FastAPI) -> None:
    app.include_router(v1_router)


def include_middleware(app: FastAPI) -> None:
    app.add_middleware(
        CorrelationIdMiddleware,
        header_name="X-Correlation-ID",
    )


def include_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(ResourceNotFoundError)
    async def resource_not_found_handler(
        request: Request, exc: ResourceNotFoundError
    ) -> JSONResponse:
        logger.warning(
            "Resource not found",
            extra={
                "error_code": exc.code,
                "error_message": exc.message,
                "error_details": exc.details,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=404,
            content=exc.to_dict(),
        )

    @app.exception_handler(ValidationError)
    async def validation_error_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        logger.warning(
            "Validation error",
            extra={
                "error_code": exc.code,
                "error_message": exc.message,
                "error_details": exc.details,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=422,
            content=exc.to_dict(),
        )

    @app.exception_handler(ExternalServiceError)
    async def external_service_error_handler(
        request: Request, exc: ExternalServiceError
    ) -> JSONResponse:
        logger.error(
            "External service error",
            extra={
                "error_code": exc.code,
                "error_message": exc.message,
                "error_details": exc.details,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=502,
            content=exc.to_dict(),
        )

    @app.exception_handler(ProcessingError)
    async def processing_error_handler(
        request: Request, exc: ProcessingError
    ) -> JSONResponse:
        logger.error(
            "Processing error",
            extra={
                "error_code": exc.code,
                "error_message": exc.message,
                "error_details": exc.details,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=500,
            content=exc.to_dict(),
        )

    @app.exception_handler(ApplicationError)
    async def application_error_handler(
        request: Request, exc: ApplicationError
    ) -> JSONResponse:
        logger.error(
            "Application error",
            extra={
                "error_code": exc.code,
                "error_message": exc.message,
                "error_details": exc.details,
                "path": request.url.path,
            },
        )
        return JSONResponse(
            status_code=500,
            content=exc.to_dict(),
        )


@asynccontextmanager
async def lifespan(app: FastAPI) -> tp.AsyncGenerator[None, None]:
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield


app = FastAPI(
    debug=settings.DEBUG,
    lifespan=lifespan,
)

include_routes(app)
include_middleware(app)
include_exception_handlers(app)
