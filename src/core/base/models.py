#! This file MUST not import __future__ __annotations__ because it triggers a bug in SQLAlchemy
import typing as tp
import uuid
from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.sql.elements import BinaryExpression
from sqlmodel import Field, SQLModel, select
from sqlmodel.ext.asyncio.session import AsyncSession

from src.core.utils.datetime import now


class DBModel(SQLModel):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
    )
    created_at: datetime = Field(
        default_factory=now,
        nullable=False,
        sa_type=DateTime(timezone=True),
    )
    deleted_at: datetime | None = Field(
        default=None,
        nullable=True,
        index=True,
        sa_type=DateTime(timezone=True),
    )
    updated_at: datetime = Field(
        default_factory=now,
        nullable=False,
        sa_type=DateTime(timezone=True),
    )

    @classmethod
    async def filter(
        cls,
        session: AsyncSession,
        *,
        filters: list[BinaryExpression] | None = None,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[tp.Self]:
        stmt = select(cls)
        if filters:
            stmt = stmt.where(*filters)

        if limit:
            stmt = stmt.limit(limit)

        if offset:
            stmt = stmt.offset(offset)

        result = await session.exec(stmt)
        return result.all()  # type: ignore

    @classmethod
    async def get_by_id(
        cls,
        session: AsyncSession,
        *,
        id: uuid.UUID,
    ) -> tp.Self | None:
        stmt = select(cls).where(cls.id == id)
        result = await session.exec(stmt)
        return result.one_or_none()
