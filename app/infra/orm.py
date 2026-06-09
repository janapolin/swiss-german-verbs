"""SQLAlchemy 2.x table definitions mirroring the data model in CLAUDE.md §11.

Content tables (`verbs`, `verb_forms`) are rebuildable from `ingestion/ingest.py`
and never hold user progress. User-state tables (`profiles`, `review_state`,
`review_log`) are per-profile and survive content rebuilds. Every schema change
goes through an Alembic migration (§15) — never hand-edit these.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _utcnow() -> datetime:
    return datetime.now(UTC)


# --- Content tables ----------------------------------------------------------


class VerbRow(Base):
    __tablename__ = "verbs"

    id: Mapped[int] = mapped_column(primary_key=True)
    infinitive: Mapped[str] = mapped_column(unique=True, index=True)
    english_gloss: Mapped[str]
    frequency_rank: Mapped[int] = mapped_column(index=True)
    verb_class: Mapped[str | None]
    separable_prefix: Mapped[str | None]
    aux: Mapped[str]
    has_konjunktiv2: Mapped[bool] = mapped_column(default=False)
    is_auxiliary: Mapped[bool] = mapped_column(default=False)
    notes: Mapped[str] = mapped_column(default="")

    forms: Mapped[list[VerbFormRow]] = relationship(
        back_populates="verb", cascade="all, delete-orphan"
    )


class VerbFormRow(Base):
    __tablename__ = "verb_forms"
    __table_args__ = (UniqueConstraint("verb_id", "form_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    verb_id: Mapped[int] = mapped_column(ForeignKey("verbs.id"), index=True)
    form_key: Mapped[str]
    value: Mapped[str]
    is_override: Mapped[bool] = mapped_column(default=False)

    verb: Mapped[VerbRow] = relationship(back_populates="forms")


# --- User-state tables --------------------------------------------------------


class ProfileRow(Base):
    __tablename__ = "profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(unique=True)
    created_at: Mapped[datetime] = mapped_column(default=_utcnow)

    # Per-profile tense drill toggles (all on by default — existing profiles
    # keep practicing everything until they opt out via Settings).
    tense_present_enabled: Mapped[bool] = mapped_column(default=True)
    tense_perfect_enabled: Mapped[bool] = mapped_column(default=True)
    tense_future_enabled: Mapped[bool] = mapped_column(default=True)
    tense_konj2_enabled: Mapped[bool] = mapped_column(default=True)


class VerbEnablementRow(Base):
    """Per-profile verb allow-list (user-state — survives content rebuilds, §11).

    Sparse-by-design would also work, but storing one row per (profile, verb)
    makes "Enable All"/"Disable All" trivial bulk updates and keeps "is this verb
    in rotation for this profile" a single indexed lookup with no default-handling
    at query time (defaults are seeded lazily on first access instead).
    """

    __tablename__ = "verb_enablement"
    __table_args__ = (UniqueConstraint("profile_id", "verb_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    verb_id: Mapped[int] = mapped_column(ForeignKey("verbs.id"), index=True)
    enabled: Mapped[bool] = mapped_column(default=True)


class ReviewStateRow(Base):
    __tablename__ = "review_state"
    __table_args__ = (UniqueConstraint("profile_id", "card_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    card_key: Mapped[str]
    ease_factor: Mapped[float]
    interval_days: Mapped[int]
    repetitions: Mapped[int]
    lapses: Mapped[int]
    due_date: Mapped[date] = mapped_column(index=True)
    last_reviewed_at: Mapped[date | None]


class ReviewLogRow(Base):
    """Append-only log of every grade given, for the history view (§14, §11)."""

    __tablename__ = "review_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    profile_id: Mapped[int] = mapped_column(ForeignKey("profiles.id"), index=True)
    card_key: Mapped[str]
    grade: Mapped[str]
    reviewed_at: Mapped[datetime] = mapped_column(default=_utcnow)
