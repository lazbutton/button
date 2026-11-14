"""The journal of the gestures on the bank and the carts (FON-66, FON-71).

A gesture is one lot: who, when, what, and how many titles. Each of its changes keeps
the title, the field, the value before and the new one, so that the lot can be undone.
SEC-10 extends the same table to the clocks, the carts' settings and the accounts.

Instants are naive UTC, like the other new tables (``radiotomate.models.agenda``).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String, select
from sqlalchemy.dialects.sqlite import DATETIME, JSON
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.orm import Session as ormSession

from radiotomate.db import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class JournalEntry(Base):
    """One gesture: a lot of titles corrected, renamed, moved or removed."""

    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # "edit", "undo", "move" (ARC-09); later "accept" (FON-27), "rename" (FON-68),
    # "remove" (FON-71)
    gesture: Mapped[str] = mapped_column(String, nullable=False, index=True)
    username: Mapped[str] = mapped_column(String, nullable=False, index=True)
    created: Mapped[datetime] = mapped_column(
        DATETIME, nullable=False, default=_utcnow, index=True
    )
    titles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # the gesture that this one undoes
    undo_of: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    details: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )

    changes: Mapped[list[JournalChange]] = relationship(
        back_populates="entry",
        cascade="all, delete-orphan",
        order_by="JournalChange.id",
    )

    @classmethod
    async def from_id(cls, session: ormSession, entry_id: int) -> JournalEntry | None:
        return await session.scalar(select(cls).where(cls.id == entry_id))

    @classmethod
    def note(
        cls,
        gesture: str,
        username: str,
        changes: list[JournalChange],
        *,
        undo_of: int | None = None,
        details: dict | None = None,
    ) -> JournalEntry:
        """A gesture to add to the session: its changes, and how many titles they
        touch. The caller adds it and commits, with what the gesture wrote.

        A move or a rename (ARC-09, FON-68) notes one change per title, field
        ``path``, from the old path to the new one, status ``done``.
        """
        titles = {change.beets_id or change.path for change in changes}
        fields = sorted({change.field for change in changes})
        return cls(
            gesture=gesture,
            username=username,
            titles=len(titles),
            undo_of=undo_of,
            details={"fields": fields, **(details or {})},
            changes=changes,
        )


class JournalChange(Base):
    """One field of one title, in one gesture."""

    __tablename__ = "journal_changes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    entry_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("journal_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    beets_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    # the file's path when the gesture was made, as Beets keeps it
    path: Mapped[str] = mapped_column(String, nullable=False, default="")
    # artist and title when the gesture was made, for a title gone since
    label: Mapped[str] = mapped_column(String, nullable=False, default="")
    field: Mapped[str] = mapped_column(String, nullable=False)
    old_value: Mapped[object] = mapped_column(JSON, nullable=True)
    new_value: Mapped[object] = mapped_column(JSON, nullable=True)
    # "pending" while it is written, "done", "waiting" (on air or queued),
    # "kept" (changed since: not written), "cancelled", "failed"
    status: Mapped[str] = mapped_column(
        String, nullable=False, default="pending", index=True
    )
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    applied_at: Mapped[datetime | None] = mapped_column(DATETIME, nullable=True)

    entry: Mapped[JournalEntry] = relationship(back_populates="changes")
