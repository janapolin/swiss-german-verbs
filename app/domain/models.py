"""Frozen domain dataclasses: Verb, VerbForms, Card, ReviewState (§11).

These mirror the content/user-state tables but are framework-free — no ORM,
no Pydantic. Repositories translate to/from these; routes never see rows.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.domain.enums import Person, Tense

Aux = Literal["ha", "si"]
VerbClass = Literal["A", "B", "C"]


@dataclass(frozen=True, slots=True)
class Verb:
    """A verb's metadata row (mirrors the `verbs` table, §11)."""

    id: int
    infinitive: str
    english_gloss: str
    frequency_rank: int
    aux: Aux
    has_konjunktiv2: bool = False
    is_auxiliary: bool = False
    verb_class: VerbClass | None = None
    separable_prefix: str | None = None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class VerbForms:
    """The stored conjugation forms for one verb — always *bare* for separables,
    prefix stripped (§5).

    `overrides` carries any cell whose `verb_forms` row has `is_override = true`:
    a full pre-assembled "pronoun + form[ + prefix]" string that bypasses
    rule-based assembly entirely (§6 override hook), keyed by the (tense, person)
    cell it replaces.
    """

    verb_id: int
    present_sg1: str
    present_sg2: str
    present_sg3: str
    present_pl: str
    participle: str
    konj2_sg1: str | None = None
    konj2_sg2: str | None = None
    konj2_sg3: str | None = None
    konj2_pl: str | None = None
    overrides: Mapping[tuple[Tense, Person], str] = field(default_factory=dict)

    def present(self, person: Person) -> str:
        return {
            Person.SG1: self.present_sg1,
            Person.SG2: self.present_sg2,
            Person.SG3: self.present_sg3,
            Person.PL: self.present_pl,
        }[person]

    def konj2(self, person: Person) -> str | None:
        return {
            Person.SG1: self.konj2_sg1,
            Person.SG2: self.konj2_sg2,
            Person.SG3: self.konj2_sg3,
            Person.PL: self.konj2_pl,
        }[person]


@dataclass(frozen=True, slots=True)
class Card:
    """A `(verb × tense × person)` slot — the unit SRS state is tracked against (§4)."""

    card_key: str
    verb_id: int
    tense: Tense
    person: Person


@dataclass(frozen=True, slots=True)
class ReviewState:
    """Per-profile SRS progress for one card (mirrors `review_state`, §11)."""

    profile_id: int
    card_key: str
    due_date: date
    ease_factor: float = 2.5
    interval_days: int = 0
    repetitions: int = 0
    lapses: int = 0
    last_reviewed_at: date | None = None
