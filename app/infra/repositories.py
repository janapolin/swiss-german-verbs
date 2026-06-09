"""VerbRepository, ReviewRepository, ProfileRepository — the only code that
talks to the ORM (§3, §15). Routes and services see domain dataclasses only;
everything ORM-shaped is translated to/from them right here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domain.enums import Grade, Person, Tense
from app.domain.models import Aux, ReviewState, Verb, VerbForms
from app.domain.rendering import (
    HAA_INFINITIVE,
    SII_INFINITIVE,
    WERDE_INFINITIVE,
    AuxiliaryForms,
)
from app.infra.orm import (
    ProfileRow,
    ReviewLogRow,
    ReviewStateRow,
    VerbEnablementRow,
    VerbFormRow,
    VerbRow,
)

# Stored-form keys in (sg1, sg2, sg3, pl) order — matches `Person`'s declaration
# order and the 4-tuples `VerbRepository.create`/`update` accept (§5).
_PRESENT_FORM_KEYS: tuple[str, str, str, str] = (
    "present_sg1",
    "present_sg2",
    "present_sg3",
    "present_pl",
)
_KONJ2_FORM_KEYS: tuple[str, str, str, str] = ("konj2_sg1", "konj2_sg2", "konj2_sg3", "konj2_pl")

# form_key -> the single (tense, person) cell it overrides when is_override=true.
# `participle` has no such mapping: it's always stored as-is, never rule-assembled.
_OVERRIDABLE_CELLS: dict[str, tuple[Tense, Person]] = {
    "present_sg1": (Tense.PRESENT, Person.SG1),
    "present_sg2": (Tense.PRESENT, Person.SG2),
    "present_sg3": (Tense.PRESENT, Person.SG3),
    "present_pl": (Tense.PRESENT, Person.PL),
    "konj2_sg1": (Tense.KONJ2, Person.SG1),
    "konj2_sg2": (Tense.KONJ2, Person.SG2),
    "konj2_sg3": (Tense.KONJ2, Person.SG3),
    "konj2_pl": (Tense.KONJ2, Person.PL),
}


def _to_verb(row: VerbRow) -> Verb:
    return Verb(
        id=row.id,
        infinitive=row.infinitive,
        english_gloss=row.english_gloss,
        frequency_rank=row.frequency_rank,
        aux=row.aux,  # type: ignore[arg-type]  # DB constrains to 'ha'|'si' (§11)
        has_konjunktiv2=row.has_konjunktiv2,
        is_auxiliary=row.is_auxiliary,
        verb_class=row.verb_class,  # type: ignore[arg-type]  # DB constrains to A|B|C|null
        separable_prefix=row.separable_prefix,
        notes=row.notes,
    )


def _to_verb_forms(verb_id: int, rows: Sequence[VerbFormRow]) -> VerbForms:
    values = {row.form_key: row.value for row in rows}
    overrides = {
        _OVERRIDABLE_CELLS[row.form_key]: row.value
        for row in rows
        if row.is_override and row.form_key in _OVERRIDABLE_CELLS
    }
    return VerbForms(
        verb_id=verb_id,
        present_sg1=values["present_sg1"],
        present_sg2=values["present_sg2"],
        present_sg3=values["present_sg3"],
        present_pl=values["present_pl"],
        participle=values["participle"],
        konj2_sg1=values.get("konj2_sg1"),
        konj2_sg2=values.get("konj2_sg2"),
        konj2_sg3=values.get("konj2_sg3"),
        konj2_pl=values.get("konj2_pl"),
        overrides=overrides,
    )


class VerbRepository:
    """Read access to the content tables (`verbs`, `verb_forms`, §11)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get_by_id(self, verb_id: int) -> Verb | None:
        row = self._session.get(VerbRow, verb_id)
        return _to_verb(row) if row else None

    def get_by_infinitive(self, infinitive: str) -> Verb | None:
        row = self._session.scalar(select(VerbRow).where(VerbRow.infinitive == infinitive))
        return _to_verb(row) if row else None

    def list_all(self) -> list[Verb]:
        """All verbs, ordered by `frequency_rank` ascending (§10, §13)."""
        rows = self._session.scalars(select(VerbRow).order_by(VerbRow.frequency_rank)).all()
        return [_to_verb(row) for row in rows]

    def get_forms(self, verb_id: int) -> VerbForms | None:
        rows = self._session.scalars(
            select(VerbFormRow).where(VerbFormRow.verb_id == verb_id)
        ).all()
        return _to_verb_forms(verb_id, rows) if rows else None

    def create(
        self,
        *,
        infinitive: str,
        english_gloss: str,
        aux: Aux,
        separable_prefix: str | None,
        notes: str,
        present: tuple[str, str, str, str],
        participle: str,
        konj2: tuple[str, str, str, str] | None,
    ) -> Verb:
        """Add a user-entered verb (Part 5). Appended to the end of the
        frequency ranking (§13: "owner can reorder later"); `verb_class` is
        ingestion-pipeline metadata the renderer never reads, so `None` here
        is harmless."""
        next_rank = (self._session.scalar(select(func.max(VerbRow.frequency_rank))) or 0) + 1
        row = VerbRow(
            infinitive=infinitive,
            english_gloss=english_gloss,
            frequency_rank=next_rank,
            verb_class=None,
            separable_prefix=separable_prefix,
            aux=aux,
            has_konjunktiv2=konj2 is not None,
            is_auxiliary=False,
            notes=notes,
        )
        self._session.add(row)
        self._session.flush()
        self._replace_forms(row.id, present=present, participle=participle, konj2=konj2)
        return _to_verb(row)

    def update(
        self,
        verb_id: int,
        *,
        infinitive: str,
        english_gloss: str,
        aux: Aux,
        separable_prefix: str | None,
        notes: str,
        present: tuple[str, str, str, str],
        participle: str,
        konj2: tuple[str, str, str, str] | None,
    ) -> Verb:
        row = self._session.get(VerbRow, verb_id)
        if row is None:
            raise LookupError(f"verb {verb_id} not found")
        row.infinitive = infinitive
        row.english_gloss = english_gloss
        row.separable_prefix = separable_prefix
        row.aux = aux
        row.has_konjunktiv2 = konj2 is not None
        row.notes = notes
        self._session.flush()
        self._replace_forms(verb_id, present=present, participle=participle, konj2=konj2)
        return _to_verb(row)

    def _replace_forms(
        self,
        verb_id: int,
        *,
        present: tuple[str, str, str, str],
        participle: str,
        konj2: tuple[str, str, str, str] | None,
    ) -> None:
        """Overwrite all stored cells for a verb (§5) — simplest correct option
        for hand-edited verbs; `is_override` stays `False` (no rule-assembly to
        bypass for user-entered forms)."""
        self._session.execute(VerbFormRow.__table__.delete().where(VerbFormRow.verb_id == verb_id))
        values: dict[str, str] = dict(zip(_PRESENT_FORM_KEYS, present, strict=True))
        values["participle"] = participle
        if konj2 is not None:
            values.update(dict(zip(_KONJ2_FORM_KEYS, konj2, strict=True)))
        for form_key, value in values.items():
            self._session.add(VerbFormRow(verb_id=verb_id, form_key=form_key, value=value))
        self._session.flush()

    def get_auxiliary_forms(self) -> AuxiliaryForms:
        """Load haa/sii/wèèrde's present tables by infinitive (§6, §9): the
        rendering engine needs these to assemble perfect/future/konj2 cells.
        """

        def forms_for(infinitive: str) -> VerbForms:
            verb = self.get_by_infinitive(infinitive)
            if verb is None:
                raise LookupError(f"auxiliary {infinitive!r} not found — run `ingest.py` first")
            forms = self.get_forms(verb.id)
            if forms is None:
                raise LookupError(f"auxiliary {infinitive!r} has no stored forms")
            return forms

        return AuxiliaryForms(
            haa=forms_for(HAA_INFINITIVE),
            sii=forms_for(SII_INFINITIVE),
            werde=forms_for(WERDE_INFINITIVE),
        )


def _to_review_state(row: ReviewStateRow) -> ReviewState:
    return ReviewState(
        profile_id=row.profile_id,
        card_key=row.card_key,
        due_date=row.due_date,
        ease_factor=row.ease_factor,
        interval_days=row.interval_days,
        repetitions=row.repetitions,
        lapses=row.lapses,
        last_reviewed_at=row.last_reviewed_at,
    )


class ReviewRepository:
    """Read/write access to the user-state tables (`review_state`, `review_log`, §11)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, profile_id: int, card_key: str) -> ReviewState | None:
        row = self._get_row(profile_id, card_key)
        return _to_review_state(row) if row else None

    def list_due(self, profile_id: int, today: date) -> list[ReviewState]:
        """Due reviews, ordered by `due_date` ascending (§10 step 1)."""
        rows = self._session.scalars(
            select(ReviewStateRow)
            .where(ReviewStateRow.profile_id == profile_id, ReviewStateRow.due_date <= today)
            .order_by(ReviewStateRow.due_date)
        ).all()
        return [_to_review_state(row) for row in rows]

    def list_known_card_keys(self, profile_id: int) -> frozenset[str]:
        """Every card_key with a `review_state` row for this profile — i.e. every
        card that's been introduced at least once (§10 step 2: a card not in this
        set is "new"; the row is created lazily on a card's first grade)."""
        rows = self._session.scalars(
            select(ReviewStateRow.card_key).where(ReviewStateRow.profile_id == profile_id)
        ).all()
        return frozenset(rows)

    def get_many(self, profile_id: int, card_keys: Sequence[str]) -> dict[str, ReviewState]:
        """Batch-fetch review states for a set of card keys, keyed by `card_key`
        (verb-detail's star ratings need one query for all of a verb's slots,
        not one per slot)."""
        if not card_keys:
            return {}
        rows = self._session.scalars(
            select(ReviewStateRow).where(
                ReviewStateRow.profile_id == profile_id,
                ReviewStateRow.card_key.in_(card_keys),
            )
        ).all()
        return {row.card_key: _to_review_state(row) for row in rows}

    def upsert(self, state: ReviewState) -> None:
        """Create or update the `(profile_id, card_key)` row (§10: created lazily
        on first encounter, then updated on every grade)."""
        row = self._get_row(state.profile_id, state.card_key)
        if row is None:
            row = ReviewStateRow(profile_id=state.profile_id, card_key=state.card_key)
            self._session.add(row)
        row.ease_factor = state.ease_factor
        row.interval_days = state.interval_days
        row.repetitions = state.repetitions
        row.lapses = state.lapses
        row.due_date = state.due_date
        row.last_reviewed_at = state.last_reviewed_at
        self._session.flush()

    def log_grade(
        self, profile_id: int, card_key: str, grade: Grade, reviewed_at: datetime
    ) -> None:
        """Append-only review log (§11) — also the source of "introduced today" counts."""
        self._session.add(
            ReviewLogRow(
                profile_id=profile_id, card_key=card_key, grade=grade.value, reviewed_at=reviewed_at
            )
        )
        self._session.flush()

    def count_reviews_today(self, profile_id: int, today: date) -> int:
        """Total grades submitted today, of any kind (§14: drives the practice
        screen's "Daily goal N / target" progress counter)."""
        stmt = select(func.count()).select_from(ReviewLogRow).where(
            ReviewLogRow.profile_id == profile_id,
            func.date(ReviewLogRow.reviewed_at) == today.isoformat(),
        )
        return self._session.scalar(stmt) or 0

    def count_reviews_total(self, profile_id: int) -> int:
        """All-time grade count from the append-only `review_log` (profile-stats block)."""
        stmt = select(func.count()).select_from(ReviewLogRow).where(
            ReviewLogRow.profile_id == profile_id
        )
        return self._session.scalar(stmt) or 0

    def count_cards_seen(self, profile_id: int) -> int:
        """Distinct card slots with a `review_state` row — `UNIQUE(profile_id,
        card_key)` makes a plain row count equivalent to a distinct count."""
        stmt = select(func.count()).select_from(ReviewStateRow).where(
            ReviewStateRow.profile_id == profile_id
        )
        return self._session.scalar(stmt) or 0

    def _get_row(self, profile_id: int, card_key: str) -> ReviewStateRow | None:
        return self._session.scalar(
            select(ReviewStateRow).where(
                ReviewStateRow.profile_id == profile_id, ReviewStateRow.card_key == card_key
            )
        )


_TENSE_FLAG_FIELDS: dict[Tense, str] = {
    Tense.PRESENT: "tense_present_enabled",
    Tense.PERFECT: "tense_perfect_enabled",
    Tense.FUTURE: "tense_future_enabled",
    Tense.KONJ2: "tense_konj2_enabled",
}


@dataclass(frozen=True, slots=True)
class Profile:
    """A learner profile (§1: schema must support multiple profiles from day one)."""

    id: int
    name: str
    created_at: datetime
    tense_present_enabled: bool = True
    tense_perfect_enabled: bool = True
    tense_future_enabled: bool = True
    tense_konj2_enabled: bool = True

    def enabled_tenses(self) -> frozenset[Tense]:
        """Which tenses this profile currently drills — the on/off toggles
        configured in Settings, in any combination."""
        return frozenset(
            tense for tense, field in _TENSE_FLAG_FIELDS.items() if getattr(self, field)
        )


def _to_profile(row: ProfileRow) -> Profile:
    return Profile(
        id=row.id,
        name=row.name,
        created_at=row.created_at,
        tense_present_enabled=row.tense_present_enabled,
        tense_perfect_enabled=row.tense_perfect_enabled,
        tense_future_enabled=row.tense_future_enabled,
        tense_konj2_enabled=row.tense_konj2_enabled,
    )


class ProfileRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_all(self) -> list[Profile]:
        rows = self._session.scalars(select(ProfileRow).order_by(ProfileRow.id)).all()
        return [_to_profile(row) for row in rows]

    def get(self, profile_id: int) -> Profile | None:
        row = self._session.get(ProfileRow, profile_id)
        return _to_profile(row) if row else None

    def create(self, name: str) -> Profile:
        row = ProfileRow(name=name)
        self._session.add(row)
        self._session.flush()
        return _to_profile(row)

    def rename(self, profile_id: int, name: str) -> Profile:
        row = self._require_row(profile_id)
        row.name = name
        self._session.flush()
        return _to_profile(row)

    def set_tense_filters(self, profile_id: int, enabled: frozenset[Tense]) -> Profile:
        """Persist the on/off state of all four tense toggles at once — the
        Settings form always submits the full set, so partial updates don't arise."""
        row = self._require_row(profile_id)
        for tense, field in _TENSE_FLAG_FIELDS.items():
            setattr(row, field, tense in enabled)
        self._session.flush()
        return _to_profile(row)

    def delete(self, profile_id: int) -> None:
        """Remove a profile and all of its user-state rows (§11 — review_state,
        review_log, verb_enablement are per-profile and don't outlive it).

        Explicit cascade rather than a DB-level `ondelete="CASCADE"`: SQLite only
        enforces FK actions with `PRAGMA foreign_keys=ON`, which this app doesn't
        enable, so relying on it would silently leave orphaned rows.
        """
        self._session.execute(
            ReviewStateRow.__table__.delete().where(ReviewStateRow.profile_id == profile_id)
        )
        self._session.execute(
            ReviewLogRow.__table__.delete().where(ReviewLogRow.profile_id == profile_id)
        )
        self._session.execute(
            VerbEnablementRow.__table__.delete().where(VerbEnablementRow.profile_id == profile_id)
        )
        row = self._session.get(ProfileRow, profile_id)
        if row is not None:
            self._session.delete(row)
        self._session.flush()

    def _require_row(self, profile_id: int) -> ProfileRow:
        row = self._session.get(ProfileRow, profile_id)
        if row is None:
            raise LookupError(f"profile {profile_id} not found")
        return row


class VerbEnablementRepository:
    """Per-profile verb allow-list (§11 user-state — survives content rebuilds).

    A brand-new profile has no rows here; `list_enabled_verb_ids` seeds sensible
    defaults (top N by `frequency_rank` enabled, the rest disabled) the first
    time it's queried, so callers never need to special-case "no rows yet".
    """

    def __init__(self, session: Session, *, default_enabled_count: int) -> None:
        self._session = session
        self._default_enabled_count = default_enabled_count

    def list_enabled_verb_ids(self, profile_id: int) -> frozenset[int]:
        self._ensure_seeded(profile_id)
        rows = self._session.scalars(
            select(VerbEnablementRow.verb_id).where(
                VerbEnablementRow.profile_id == profile_id, VerbEnablementRow.enabled.is_(True)
            )
        ).all()
        return frozenset(rows)

    def list_all(self, profile_id: int) -> dict[int, bool]:
        """`verb_id -> enabled` for every verb, for rendering the Verbs list/toggles."""
        self._ensure_seeded(profile_id)
        rows = self._session.scalars(
            select(VerbEnablementRow).where(VerbEnablementRow.profile_id == profile_id)
        ).all()
        return {row.verb_id: row.enabled for row in rows}

    def is_enabled(self, profile_id: int, verb_id: int) -> bool:
        """Current state of one verb's toggle — `False` if no row exists yet."""
        self._ensure_seeded(profile_id)
        row = self._get_row(profile_id, verb_id)
        return row.enabled if row is not None else False

    def set_enabled(self, profile_id: int, verb_id: int, enabled: bool) -> bool:
        """Flip one verb's toggle; returns the new state."""
        self._ensure_seeded(profile_id)
        row = self._get_row(profile_id, verb_id)
        if row is None:
            row = VerbEnablementRow(profile_id=profile_id, verb_id=verb_id, enabled=enabled)
            self._session.add(row)
        else:
            row.enabled = enabled
        self._session.flush()
        return row.enabled

    def set_all(self, profile_id: int, *, enabled: bool) -> None:
        """"Enable All" / "Disable All" — bulk-flip every verb for this profile."""
        self._ensure_seeded(profile_id)
        self._session.execute(
            VerbEnablementRow.__table__.update()
            .where(VerbEnablementRow.profile_id == profile_id)
            .values(enabled=enabled)
        )
        self._session.flush()

    def _ensure_seeded(self, profile_id: int) -> None:
        has_rows = self._session.scalar(
            select(VerbEnablementRow.id).where(VerbEnablementRow.profile_id == profile_id).limit(1)
        )
        if has_rows is not None:
            return
        verb_ids_by_rank = self._session.scalars(
            select(VerbRow.id).order_by(VerbRow.frequency_rank)
        ).all()
        for index, verb_id in enumerate(verb_ids_by_rank):
            self._session.add(
                VerbEnablementRow(
                    profile_id=profile_id,
                    verb_id=verb_id,
                    enabled=index < self._default_enabled_count,
                )
            )
        self._session.flush()

    def _get_row(self, profile_id: int, verb_id: int) -> VerbEnablementRow | None:
        return self._session.scalar(
            select(VerbEnablementRow).where(
                VerbEnablementRow.profile_id == profile_id, VerbEnablementRow.verb_id == verb_id
            )
        )
