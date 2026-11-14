"""The fiches of the library (FON-25, v22): see `commands/update/v22.py`."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.sqlite import DATETIME, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from radiotomate.db import Base

# Where the search of a title is.
FOUND = "trouvé"
CLOSE = "rapproché"
NOT_FOUND = "introuvable"
SET_ASIDE = "écarté"
FAILED = "erreur"

# The states of a proposition.
PROPOSED = "proposée"
ACCEPTED = "acceptée"
WRITTEN = "écrite"
REFUSED = "refusée"
STALE = "périmée"
REVERTED = "revenue"
WRITE_FAILED = "en erreur"

# A decision.
ACCEPT = "acceptée"
REFUSE = "refusée"


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Fiche(Base):
    """A title searched, by its Beets id."""

    __tablename__ = "fiches"
    __table_args__ = (UniqueConstraint("beets_id", name="uq_fiches_beets_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    beets_id: Mapped[int] = mapped_column(Integer, nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    text_key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False)
    reasons: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String, nullable=False, default="")
    url: Mapped[str] = mapped_column(String, nullable=False, default="")
    rules_version: Mapped[int] = mapped_column(Integer, nullable=False)
    evidence: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str] = mapped_column(String, nullable=False, default="")
    searched_at: Mapped[datetime] = mapped_column(
        DATETIME, nullable=False, default=utcnow
    )
    next_at: Mapped[datetime | None] = mapped_column(
        DATETIME, nullable=True, index=True
    )
    created: Mapped[datetime] = mapped_column(DATETIME, nullable=False, default=utcnow)
    modified: Mapped[datetime] = mapped_column(
        DATETIME, nullable=False, default=utcnow, onupdate=utcnow
    )

    propositions: Mapped[list[FicheProposition]] = relationship(
        back_populates="fiche",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="FicheProposition.id",
    )


class FicheProposition(Base):
    """A field proposed for a fiche."""

    __tablename__ = "fiche_propositions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    fiche_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("fiches.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    field: Mapped[str] = mapped_column(String, nullable=False)
    before: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    level: Mapped[str] = mapped_column(String, nullable=False)
    why: Mapped[str] = mapped_column(String, nullable=False, default="")
    source: Mapped[str] = mapped_column(String, nullable=False, default="")
    state: Mapped[str] = mapped_column(String, nullable=False, default=PROPOSED)
    error: Mapped[str] = mapped_column(String, nullable=False, default="")
    created: Mapped[datetime] = mapped_column(DATETIME, nullable=False, default=utcnow)
    modified: Mapped[datetime] = mapped_column(
        DATETIME, nullable=False, default=utcnow, onupdate=utcnow
    )

    fiche: Mapped[Fiche] = relationship(back_populates="propositions")


class FicheDecision(Base):
    """An acceptance or a refusal, by the key of the title, the field and the value."""

    __tablename__ = "fiche_decisions"
    __table_args__ = (
        UniqueConstraint(
            "key", "field", "value", name="uq_fiche_decisions_key_field_value"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String, nullable=False, index=True)
    field: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    decision: Mapped[str] = mapped_column(String, nullable=False)
    username: Mapped[str] = mapped_column(String, nullable=False)
    decided_at: Mapped[datetime] = mapped_column(
        DATETIME, nullable=False, default=utcnow
    )
