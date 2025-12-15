import asyncio
import tempfile
import typing as tp
from pathlib import Path

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession
from testcontainers.postgres import PostgresContainer

from src.api.app import app
from src.api.dependencies import get_session

DOCS_DIR = Path(__file__).parent / "docs"


@pytest.fixture(scope="session")
def connection_url() -> tp.Generator[str, None, None]:
    with PostgresContainer(
        image="postgres:18.1-alpine",
        driver="asyncpg",
    ) as postgres:
        yield postgres.get_connection_url()


@pytest_asyncio.fixture(scope="function")
async def engine(connection_url: str) -> tp.AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(connection_url)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    yield engine


@pytest_asyncio.fixture(scope="function")
async def session(engine: AsyncEngine) -> tp.AsyncGenerator[AsyncSession, None]:
    SessionFactory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with SessionFactory() as _session:
        yield _session


@pytest_asyncio.fixture(scope="function")
async def client_session(engine: AsyncEngine) -> tp.AsyncGenerator[AsyncSession, None]:
    SessionFactory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with SessionFactory() as _session:
        yield _session


@pytest.fixture(scope="function")
def event_loop() -> tp.Generator[asyncio.AbstractEventLoop, None, None]:
    policy = asyncio.get_event_loop_policy()
    loop = policy.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def client(client_session: AsyncSession) -> AsyncClient:
    app.dependency_overrides[get_session] = lambda: client_session
    client = AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    )
    return client


@pytest.fixture
def contrato_social_pdf() -> bytes:
    """Load a sample contrato social PDF for testing."""
    pdf_path = DOCS_DIR / "Tech Solutions" / "01_contrato_social.pdf"
    return pdf_path.read_bytes()


@pytest.fixture
def cartao_cnpj_pdf() -> bytes:
    """Load a sample cartão CNPJ PDF for testing."""
    pdf_path = DOCS_DIR / "Tech Solutions" / "02_cartao_cnpj.pdf"
    return pdf_path.read_bytes()


@pytest.fixture
def certidao_negativa_pdf() -> bytes:
    """Load a sample certidão negativa PDF for testing."""
    pdf_path = DOCS_DIR / "Tech Solutions" / "03_certidao_negativa_federal.pdf"
    return pdf_path.read_bytes()


@pytest.fixture
def temp_storage_dir(monkeypatch: pytest.MonkeyPatch) -> tp.Generator[Path, None, None]:
    """Create a temporary directory for file storage during tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Clear the cached storage instance to force recreation with new path
        from src.core import storage

        storage.get_storage.cache_clear()

        # Patch settings to use temporary directory
        from src.core import settings

        original_settings = settings._settings
        if original_settings:
            monkeypatch.setattr(original_settings, "STORAGE_LOCAL_PATH", Path(tmpdir))

        yield Path(tmpdir)

        # Restore cached storage
        storage.get_storage.cache_clear()
