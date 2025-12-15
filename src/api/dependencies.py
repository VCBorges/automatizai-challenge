import typing as tp

from fastapi import Depends
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.database.core import get_session

SessionDep = tp.Annotated[AsyncSession, Depends(get_session)]
