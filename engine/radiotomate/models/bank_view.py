from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import DATETIME, JSON
from sqlalchemy.ext.mutable import MutableDict
from sqlalchemy.orm import Mapped, mapped_column

from radiotomate.db import Base


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class BankView(Base):
    """A view of the bank's table that an account keeps under a name (FON-65, v19)."""

    __tablename__ = "bank_views"
    __table_args__ = (
        UniqueConstraint("user_id", "name", name="uq_bank_views_user_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    state: Mapped[dict] = mapped_column(
        MutableDict.as_mutable(JSON), nullable=False, default=dict
    )
    created: Mapped[datetime] = mapped_column(DATETIME, nullable=False, default=_utcnow)
    modified: Mapped[datetime] = mapped_column(
        DATETIME, nullable=False, default=_utcnow, onupdate=_utcnow
    )
