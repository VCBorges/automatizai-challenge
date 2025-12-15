import uvicorn

from src.core.settings import get_settings

settings = get_settings()


if __name__ == "__main__":
    uvicorn.run(
        app="src.api.app:app",
        host=settings.UVICORN_HOST,
        port=settings.UVICORN_PORT,
        reload=settings.UVICORN_RELOAD,
    )
