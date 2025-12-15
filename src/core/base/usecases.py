from pydantic import BaseModel
from pydantic.config import ConfigDict

from sqlmodel.ext.asyncio.session import AsyncSession
from src.core.types import DictStrAny


class UseCase(BaseModel):
    session: AsyncSession
    correlation_id: str

    model_config = ConfigDict(
        arbitrary_types_allowed=True,
    )

    async def handle(self) -> DictStrAny:
        raise NotImplementedError
