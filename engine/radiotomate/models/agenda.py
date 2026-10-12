"""Dated broadcasts (Agenda): diffusions, their guests, files and the weekly
occurrences cancelled for a day.

``starts_at``, ``ends_at`` and every other instant here are stored as naive
UTC: unlike the rundown (Paris-naive), a dated broadcast must survive the
October hour that happens twice.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import ClassVar

from sqlalchemy import Date, Float, ForeignKey, Integer, String, Text, select
from sqlalchemy.dialects.sqlite import DATETIME, JSON
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import Session as ormSession

from radiotomate.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AgendaGuest(Base):
    """Someone invited to drop a set, reached through a private link."""

    __tablename__ = "agenda_guests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    contact: Mapped[str] = mapped_column(String, nullable=False, default="")
    token: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    token_created: Mapped[datetime] = mapped_column(
        DATETIME, nullable=False, default=_utcnow
    )
    opened_at: Mapped[datetime | None] = mapped_column(DATETIME, nullable=True)
    created: Mapped[datetime] = mapped_column(DATETIME, nullable=False, default=_utcnow)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    __mapper_args__: ClassVar[dict] = {"version_id_col": version}

    @classmethod
    async def from_id(cls, session: ormSession, guest_id: int) -> AgendaGuest | None:
        return await session.scalar(select(cls).where(cls.id == guest_id))

    @classmethod
    async def from_token(cls, session: ormSession, token: str) -> AgendaGuest | None:
        if not token:
            return None
        return await session.scalar(select(cls).where(cls.token == token))

    @classmethod
    async def all(cls, session: ormSession) -> list[AgendaGuest]:
        return list(await session.scalars(select(cls).order_by(cls.name, cls.id)))


class AgendaDiffusion(Base):
    """One broadcast at a date: a recorded set or a live show."""

    __tablename__ = "agenda_diffusions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DATETIME, nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DATETIME, nullable=False, index=True)
    guest_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agenda_guests.id", ondelete="SET NULL"),
        nullable=True,
    )
    host_username: Mapped[str] = mapped_column(String, nullable=False, default="")
    set_title: Mapped[str] = mapped_column(String, nullable=False, default="")
    tracklist: Mapped[str] = mapped_column(Text, nullable=False, default="")
    rights_at: Mapped[datetime | None] = mapped_column(DATETIME, nullable=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DATETIME, nullable=True)
    series_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    air_status: Mapped[str] = mapped_column(
        String, nullable=False, default="upcoming", index=True
    )
    air_reason: Mapped[str] = mapped_column(String, nullable=False, default="")
    air_item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    aired_start: Mapped[datetime | None] = mapped_column(DATETIME, nullable=True)
    aired_end: Mapped[datetime | None] = mapped_column(DATETIME, nullable=True)
    stop_requested_at: Mapped[datetime | None] = mapped_column(DATETIME, nullable=True)
    created_by: Mapped[str] = mapped_column(String, nullable=False, default="")
    created: Mapped[datetime] = mapped_column(DATETIME, nullable=False, default=_utcnow)
    modified: Mapped[datetime] = mapped_column(
        DATETIME, nullable=False, default=_utcnow, onupdate=_utcnow
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    guest: Mapped[AgendaGuest | None] = relationship(lazy="selectin")
    files: Mapped[list[AgendaFile]] = relationship(
        back_populates="diffusion",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="AgendaFile.id",
    )

    __mapper_args__: ClassVar[dict] = {"version_id_col": version}

    @property
    def current_file(self) -> AgendaFile | None:
        live = [row for row in self.files if row.replaced_at is None]
        return live[-1] if live else None

    @classmethod
    async def from_id(
        cls, session: ormSession, diffusion_id: int
    ) -> AgendaDiffusion | None:
        return await session.scalar(select(cls).where(cls.id == diffusion_id))

    @classmethod
    async def between(
        cls, session: ormSession, start: datetime, end: datetime
    ) -> list[AgendaDiffusion]:
        """Diffusions overlapping ``[start, end)`` (naive UTC bounds)."""
        rows = await session.scalars(
            select(cls)
            .where(cls.starts_at < end, cls.ends_at > start)
            .order_by(cls.starts_at, cls.id)
        )
        return list(rows)

    @classmethod
    async def in_status(
        cls, session: ormSession, *statuses: str
    ) -> list[AgendaDiffusion]:
        rows = await session.scalars(
            select(cls)
            .where(cls.air_status.in_(list(statuses)))
            .order_by(cls.starts_at, cls.id)
        )
        return list(rows)

    @classmethod
    async def of_guest(
        cls, session: ormSession, guest_id: int
    ) -> list[AgendaDiffusion]:
        rows = await session.scalars(
            select(cls).where(cls.guest_id == guest_id).order_by(cls.starts_at)
        )
        return list(rows)


class AgendaFile(Base):
    """The audio of a set: dropped by the guest or picked in the bank.

    ``path`` is relative to MEDIA_ROOT. ``report`` holds the analysis:
    ``status`` (pending, ok, error), format, loudness and warnings.
    """

    __tablename__ = "agenda_files"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    diffusion_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("agenda_diffusions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    path: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)
    original_name: Mapped[str] = mapped_column(String, nullable=False, default="")
    duration: Mapped[float] = mapped_column(Float, nullable=False, default=0)
    gain: Mapped[float | None] = mapped_column(Float, nullable=True)
    report: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    late: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created: Mapped[datetime] = mapped_column(DATETIME, nullable=False, default=_utcnow)
    replaced_at: Mapped[datetime | None] = mapped_column(DATETIME, nullable=True)

    diffusion: Mapped[AgendaDiffusion] = relationship(back_populates="files")

    @classmethod
    async def from_id(cls, session: ormSession, file_id: int) -> AgendaFile | None:
        return await session.scalar(select(cls).where(cls.id == file_id))

    @classmethod
    async def pending(cls, session: ormSession) -> list[AgendaFile]:
        rows = await session.scalars(
            select(cls).where(cls.replaced_at.is_(None)).order_by(cls.id)
        )
        return [row for row in rows if (row.report or {}).get("status") == "pending"]


class AgendaException(Base):
    """A weekly emission that does not happen on one Paris day."""

    __tablename__ = "agenda_exceptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    emission_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("emissions.id", ondelete="CASCADE"),
        nullable=False,
    )
    day: Mapped[date] = mapped_column(Date, nullable=False)
    created: Mapped[datetime] = mapped_column(DATETIME, nullable=False, default=_utcnow)

    @classmethod
    async def between(
        cls, session: ormSession, first: date, last: date
    ) -> list[AgendaException]:
        rows = await session.scalars(
            select(cls).where(cls.day >= first, cls.day <= last)
        )
        return list(rows)

    @classmethod
    async def find(
        cls, session: ormSession, emission_id: int, day: date
    ) -> AgendaException | None:
        return await session.scalar(
            select(cls).where(cls.emission_id == emission_id, cls.day == day)
        )
