"""Card keys + front-side metadata for a verb (§4, §9).

Enumerates the `(tense, person)` slots that exist for a verb — present/perfect/
future × 4 persons always, plus konj2 × 4 only when `has_konjunktiv2`, and only
present × 4 for auxiliaries (by default; their compound tenses are edge-casey).
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import Person, Tense
from app.domain.grammar import PERSON_LABELS, TENSE_LABELS
from app.domain.models import Card, Verb

ALL_PERSONS: tuple[Person, ...] = (Person.SG1, Person.SG2, Person.SG3, Person.PL)

# Tenses every (non-auxiliary) verb gets a slot for, regardless of has_konjunktiv2 (§4).
CORE_TENSES: tuple[Tense, ...] = (Tense.PRESENT, Tense.PERFECT, Tense.FUTURE)


def card_key(verb_id: int, tense: Tense, person: Person) -> str:
    """Stable card key, `f"{verb_id}:{tense.value}:{person.value}"` (§4)."""
    return f"{verb_id}:{tense.value}:{person.value}"


def parse_card_key(key: str) -> tuple[int, Tense, Person]:
    """Inverse of `card_key` — recovers `(verb_id, tense, person)` from a stored key.

    Needed by the session layer to turn `review_state.card_key` rows back into
    `Card`s for scheduling without a second content-table round trip.
    """
    verb_id_str, tense_str, person_str = key.split(":")
    return int(verb_id_str), Tense(tense_str), Person(person_str)


def generate_cards(verb: Verb, *, aux_present_only: bool = True) -> list[Card]:
    """Enumerate the cards that exist for `verb` (§4, §9).

    `aux_present_only` is the boolean config flag §9 calls for: when true (the
    default), auxiliaries get present-tense cards only.
    """
    if verb.is_auxiliary and aux_present_only:
        tenses: tuple[Tense, ...] = (Tense.PRESENT,)
    elif verb.has_konjunktiv2:
        tenses = (*CORE_TENSES, Tense.KONJ2)
    else:
        tenses = CORE_TENSES

    return [
        Card(card_key=card_key(verb.id, tense, person), verb_id=verb.id, tense=tense, person=person)
        for tense in tenses
        for person in ALL_PERSONS
    ]


@dataclass(frozen=True, slots=True)
class CardFront:
    """Front-side metadata for a card — what the learner sees before reveal (§12)."""

    gloss: str
    tense_label: str
    person_label: str
    # §12's sketched API shape omits this, but design_notes.md's reveal state
    # requires showing it ("the source-language infinitive appears above the
    # English gloss") — added as an additive field so both hold.
    infinitive: str


def card_front(verb: Verb, card: Card) -> CardFront:
    """Build the front-side metadata for `card` (must belong to `verb`)."""
    return CardFront(
        gloss=verb.english_gloss,
        tense_label=TENSE_LABELS[card.tense],
        person_label=PERSON_LABELS[card.person],
        infinitive=verb.infinitive,
    )
