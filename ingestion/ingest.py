"""CLI: load both seed CSVs into the content tables (§13). OFFLINE, standalone —
never imported by the running app. Idempotent: upserts by `infinitive`, so
re-running is always safe.

    python -m ingestion.ingest [--db-path PATH]

Pipeline, in the order CLAUDE.md §13 specifies:
1. Load `verbs_irregular.csv` — all forms stored as-is.
2. Load `verbs_regular.csv` — `expand_regular` generates present forms; the
   participle comes from the CSV (too irregular to generate, grammar_rules.md §3).
3. Normalize every Zdt string value (`ingestion.normalize`).
4. Detect each verb's separable prefix (`ingestion.prefixes`, longest-match —
   the source of truth here; the seed CSV's own `separable_prefix` column is
   cross-checked and only used as a fallback hint), then strip it from the
   stored present/konj2 forms and the participle so everything lands *bare* (§5).
5. Validate: all four present forms + participle present; konj2 all-or-nothing
   and consistent with `has_konjunktiv2`; `aux` is `ha`/`si`.
6. Upsert by infinitive — `frequency_rank` is assigned by estimated real-world
   usage frequency (`ingestion.frequency`, most-used first; an explicit estimate,
   not corpus data — see that module's docstring). Reorderable later without
   touching SRS state, since the card key uses `verb_id` not rank (§13).
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infra.db import REPO_ROOT, make_engine, make_session_factory
from app.infra.orm import VerbFormRow, VerbRow
from ingestion.expand_regular import expand_present
from ingestion.frequency import rank_index
from ingestion.normalize import normalize
from ingestion.prefixes import detect_separable_prefix

IRREGULAR_CSV = REPO_ROOT / "data" / "verbs_irregular.csv"
REGULAR_CSV = REPO_ROOT / "data" / "verbs_regular.csv"

_FORM_KEYS = (
    "present_sg1", "present_sg2", "present_sg3", "present_pl", "participle",
    "konj2_sg1", "konj2_sg2", "konj2_sg3", "konj2_pl",
)


@dataclass(frozen=True, slots=True)
class RawVerb:
    """A verb mid-pipeline: one row from a CSV, normalized but not yet bare."""

    infinitive: str
    english_gloss: str
    aux: str
    has_konjunktiv2: bool
    is_auxiliary: bool
    verb_class: str | None
    separable_prefix_hint: str | None
    notes: str
    present_sg1: str
    present_sg2: str
    present_sg3: str
    present_pl: str
    participle: str
    konj2_sg1: str | None
    konj2_sg2: str | None
    konj2_sg3: str | None
    konj2_pl: str | None


# --- step 1/2: load -----------------------------------------------------------


def _parse_bool(value: str) -> bool:
    return value.strip().lower() == "true"


def _none_if_blank(value: str) -> str | None:
    stripped = value.strip()
    return stripped or None


def load_irregular_rows(path: Path) -> list[RawVerb]:
    """Step 1: load `verbs_irregular.csv` — all forms stored as-is."""
    with path.open(encoding="utf-8") as handle:
        return [
            RawVerb(
                infinitive=row["infinitive"].strip(),
                english_gloss=row["english_gloss"].strip(),
                aux=row["aux"].strip(),
                has_konjunktiv2=_parse_bool(row["has_konjunktiv2"]),
                is_auxiliary=_parse_bool(row["is_auxiliary"]),
                verb_class=None,
                separable_prefix_hint=_none_if_blank(row["separable_prefix"]),
                notes=row["notes"].strip(),
                present_sg1=row["present_sg1"].strip(),
                present_sg2=row["present_sg2"].strip(),
                present_sg3=row["present_sg3"].strip(),
                present_pl=row["present_pl"].strip(),
                participle=row["participle"].strip(),
                konj2_sg1=_none_if_blank(row["konj2_sg1"]),
                konj2_sg2=_none_if_blank(row["konj2_sg2"]),
                konj2_sg3=_none_if_blank(row["konj2_sg3"]),
                konj2_pl=_none_if_blank(row["konj2_pl"]),
            )
            for row in csv.DictReader(handle)
        ]


def load_regular_rows(path: Path) -> list[RawVerb]:
    """Step 2: load `verbs_regular.csv`, generating present forms by rule.

    Regular verbs aren't auxiliaries and have no Konjunktiv II (grammar_rules.md
    §6: only the six listed irregulars do).
    """
    raw_verbs: list[RawVerb] = []
    with path.open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            verb_class = row["verb_class"].strip()
            if verb_class not in ("A", "B", "C"):
                raise ValueError(f"{row['infinitive']}: unknown verb_class {verb_class!r}")
            infinitive = row["infinitive"].strip()
            prefix_hint = _none_if_blank(row["separable_prefix"])
            present = expand_present(infinitive, verb_class, prefix_hint)  # type: ignore[arg-type]
            raw_verbs.append(
                RawVerb(
                    infinitive=infinitive,
                    english_gloss=row["english_gloss"].strip(),
                    aux=row["aux"].strip(),
                    has_konjunktiv2=False,
                    is_auxiliary=False,
                    verb_class=verb_class,
                    separable_prefix_hint=prefix_hint,
                    notes=row["notes"].strip(),
                    present_sg1=present[0],
                    present_sg2=present[1],
                    present_sg3=present[2],
                    present_pl=present[3],
                    participle=row["participle"].strip(),
                    konj2_sg1=None,
                    konj2_sg2=None,
                    konj2_sg3=None,
                    konj2_pl=None,
                )
            )
    return raw_verbs


# --- step 3: normalize ---------------------------------------------------------


def _normalize_optional(value: str | None) -> str | None:
    return normalize(value) if value is not None else None


def normalize_raw(raw: RawVerb) -> RawVerb:
    """Step 3: normalize every Zdt string (not the English gloss/notes)."""
    return replace(
        raw,
        infinitive=normalize(raw.infinitive),
        separable_prefix_hint=_normalize_optional(raw.separable_prefix_hint),
        present_sg1=normalize(raw.present_sg1),
        present_sg2=normalize(raw.present_sg2),
        present_sg3=normalize(raw.present_sg3),
        present_pl=normalize(raw.present_pl),
        participle=normalize(raw.participle),
        konj2_sg1=_normalize_optional(raw.konj2_sg1),
        konj2_sg2=_normalize_optional(raw.konj2_sg2),
        konj2_sg3=_normalize_optional(raw.konj2_sg3),
        konj2_pl=_normalize_optional(raw.konj2_pl),
    )


# --- step 4: detect + strip separable prefix -----------------------------------


def resolve_separable_prefix(raw: RawVerb) -> str | None:
    """Detect the prefix from the (normalized) infinitive — the source of truth
    per §13 step 4 — and warn if it disagrees with the seed CSV's own column
    (a data-quality signal for the owner, not a hard failure).
    """
    detected = detect_separable_prefix(raw.infinitive)
    prefix = detected[0] if detected else None
    if prefix != raw.separable_prefix_hint:
        print(
            f"  ! {raw.infinitive}: detected separable prefix {prefix!r} "
            f"disagrees with seed CSV's {raw.separable_prefix_hint!r} — using detected",
            file=sys.stderr,
        )
    return prefix


def _strip(value: str, prefix: str | None) -> str:
    return value.removeprefix(prefix) if prefix else value


def _strip_optional(value: str | None, prefix: str | None) -> str | None:
    return _strip(value, prefix) if value is not None else None


def make_bare(raw: RawVerb, prefix: str | None) -> RawVerb:
    """Strip `prefix` from every stored form so it lands bare, prefix kept
    separately in `verbs.separable_prefix` (§5, §7)."""
    return replace(
        raw,
        present_sg1=_strip(raw.present_sg1, prefix),
        present_sg2=_strip(raw.present_sg2, prefix),
        present_sg3=_strip(raw.present_sg3, prefix),
        present_pl=_strip(raw.present_pl, prefix),
        participle=_strip(raw.participle, prefix),
        konj2_sg1=_strip_optional(raw.konj2_sg1, prefix),
        konj2_sg2=_strip_optional(raw.konj2_sg2, prefix),
        konj2_sg3=_strip_optional(raw.konj2_sg3, prefix),
        konj2_pl=_strip_optional(raw.konj2_pl, prefix),
    )


# --- step 5: validate -----------------------------------------------------------


def validate(raw: RawVerb) -> None:
    """Step 5: every verb has all four present forms + participle; konj2 is
    all-or-nothing and matches `has_konjunktiv2`; `aux` is `ha`/`si`."""
    if not all((raw.present_sg1, raw.present_sg2, raw.present_sg3, raw.present_pl, raw.participle)):
        raise ValueError(f"{raw.infinitive}: missing a present form or participle")

    konj2 = (raw.konj2_sg1, raw.konj2_sg2, raw.konj2_sg3, raw.konj2_pl)
    has_all_konj2 = all(konj2)
    if any(konj2) != has_all_konj2:
        raise ValueError(f"{raw.infinitive}: konj2 forms must be all-or-nothing")
    if raw.has_konjunktiv2 != has_all_konj2:
        raise ValueError(
            f"{raw.infinitive}: has_konjunktiv2={raw.has_konjunktiv2} "
            f"but konj2 forms are {'present' if has_all_konj2 else 'absent'}"
        )
    if raw.aux not in ("ha", "si"):
        raise ValueError(f"{raw.infinitive}: aux must be 'ha' or 'si', got {raw.aux!r}")


# --- step 6: upsert -------------------------------------------------------------


def _upsert_verb_row(
    session: Session, raw: RawVerb, prefix: str | None, frequency_rank: int
) -> VerbRow:
    row = session.scalar(select(VerbRow).where(VerbRow.infinitive == raw.infinitive))
    if row is None:
        row = VerbRow(infinitive=raw.infinitive)
        session.add(row)

    row.english_gloss = raw.english_gloss
    row.frequency_rank = frequency_rank
    row.verb_class = raw.verb_class
    row.separable_prefix = prefix
    row.aux = raw.aux
    row.has_konjunktiv2 = raw.has_konjunktiv2
    row.is_auxiliary = raw.is_auxiliary
    row.notes = raw.notes
    session.flush()  # populate row.id for brand-new verbs before touching forms
    return row


def _upsert_forms(session: Session, verb_row: VerbRow, raw: RawVerb) -> None:
    values: dict[str, str | None] = {
        "present_sg1": raw.present_sg1,
        "present_sg2": raw.present_sg2,
        "present_sg3": raw.present_sg3,
        "present_pl": raw.present_pl,
        "participle": raw.participle,
        "konj2_sg1": raw.konj2_sg1,
        "konj2_sg2": raw.konj2_sg2,
        "konj2_sg3": raw.konj2_sg3,
        "konj2_pl": raw.konj2_pl,
    }
    existing = {form_row.form_key: form_row for form_row in verb_row.forms}

    for form_key in _FORM_KEYS:
        value = values[form_key]
        existing_row = existing.get(form_key)
        if value is None:
            if existing_row is not None:
                session.delete(existing_row)
            continue
        if existing_row is None:
            # `is_override` is a hand-correction mechanism (§6 override hook) —
            # ingestion never sets it; new rows start false.
            session.add(
                VerbFormRow(verb_id=verb_row.id, form_key=form_key, value=value, is_override=False)
            )
        else:
            existing_row.value = value


def upsert(session: Session, raw: RawVerb, prefix: str | None, frequency_rank: int) -> None:
    verb_row = _upsert_verb_row(session, raw, prefix, frequency_rank)
    _upsert_forms(session, verb_row, raw)


# --- orchestration --------------------------------------------------------------


def ingest(
    session: Session,
    *,
    irregular_csv: Path = IRREGULAR_CSV,
    regular_csv: Path = REGULAR_CSV,
) -> int:
    """Run the full pipeline against `session`; returns the number of verbs upserted."""
    irregulars = [normalize_raw(raw) for raw in load_irregular_rows(irregular_csv)]
    regulars = [normalize_raw(raw) for raw in load_regular_rows(regular_csv)]
    by_frequency = sorted(irregulars + regulars, key=lambda raw: rank_index(raw.infinitive))

    count = 0
    for frequency_rank, raw in enumerate(by_frequency, start=1):
        prefix = resolve_separable_prefix(raw)
        bare = make_bare(raw, prefix)
        validate(bare)
        upsert(session, bare, prefix, frequency_rank)
        count += 1

    session.commit()
    return count


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load the seed CSVs into the content tables.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=None,
        help="SQLite file to write to (defaults to data/app.db, or $SWISSVERB_DB_PATH)",
    )
    args = parser.parse_args(argv)

    engine = make_engine(args.db_path)
    session_factory = make_session_factory(engine)
    with session_factory() as session:
        count = ingest(session)

    print(f"Ingested {count} verbs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
