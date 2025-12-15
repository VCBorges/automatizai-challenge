import logging
import typing as tp

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.settings import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

engine = create_async_engine(
    settings.POSTGRES_URL,
    pool_size=4,
    max_overflow=15,
    echo=True,
    connect_args={
        "server_settings": {
            "timezone": "UTC",
        },
    },
)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_session() -> tp.AsyncGenerator[AsyncSession, None]:
    async with SessionFactory() as session:
        yield session
