"""Tests for `SessionService` (§10, §12, Part 2): no daily new-card cap, random
new-card order, and that practice respects the profile's tense/verb filters.

Runs against the real seed data via `ingest` (like `test_ingestion.py`) — the
filtering/randomization logic only matters once there's a real deck to draw from.
"""

from __future__ import annotations

import random

import pytest
from sqlalchemy.orm import Session

from app.api.services import SessionService
from app.domain.card_gen import parse_card_key
from app.domain.enums import Grade, Tense
from app.infra.db import make_engine, make_session_factory
from app.infra.orm import Base
from app.infra.repositories import ProfileRepository, VerbEnablementRepository
from ingestion.ingest import ingest


@pytest.fixture
def session() -> Session:
    engine = make_engine(":memory:")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        ingest(session)
        yield session


def _service(session: Session, *, seed: int, enabled_verb_count: int = 146) -> SessionService:
    """`enabled_verb_count=146` enables every seed verb — the default top-20
    would otherwise narrow the pool and make the spread assertions flaky."""
    return SessionService(
        session,
        aux_present_only=True,
        default_enabled_verb_count=enabled_verb_count,
        rng=random.Random(seed),
    )


def test_practicing_past_the_old_ten_card_cap_keeps_serving_new_cards(session: Session):
    """The old `daily_new_limit=10` made the deck look exhausted after ten cards
    (the bug report: "stops working after ten cards"). Grading straight through
    fifteen distinct cards must keep producing fresh ones — no `None` early-out."""
    profile = ProfileRepository(session).create("marathoner")
    service = _service(session, seed=7)

    seen_keys: set[str] = set()
    for _ in range(15):
        next_card = service.next_card(profile.id)
        assert next_card is not None, "ran dry before the old cap would have kicked in"
        assert next_card.card_key not in seen_keys
        seen_keys.add(next_card.card_key)
        service.grade_card(profile.id, next_card.card_key, Grade.GOOD)

    assert len(seen_keys) == 15


def test_new_card_order_is_randomized_across_verbs_tenses_and_persons(session: Session):
    """§1: "the initial order of cards asked [should be] completely random in
    person, tense, and word" — sampling repeatedly (without grading, so the
    "known" set never grows) must surface a real spread, not the same slot."""
    profile = ProfileRepository(session).create("sampler")
    service = _service(session, seed=42)

    verb_ids: set[int] = set()
    tenses: set[Tense] = set()
    persons = set()
    for _ in range(40):
        next_card = service.next_card(profile.id)
        assert next_card is not None
        verb_id, tense, person = parse_card_key(next_card.card_key)
        verb_ids.add(verb_id)
        tenses.add(tense)
        persons.add(person)

    assert len(verb_ids) > 5, f"expected a spread of verbs, got {verb_ids}"
    assert len(tenses) > 1, f"expected a spread of tenses, got {tenses}"
    assert len(persons) > 1, f"expected a spread of persons, got {persons}"


def test_practice_only_serves_enabled_tenses(session: Session):
    """Settings toggles (Part 3) must take effect immediately — disabling a
    tense removes it from the new-card pool right away, not just for new
    introductions going forward."""
    profiles = ProfileRepository(session)
    profile = profiles.create("present-only")
    profiles.set_tense_filters(profile.id, frozenset({Tense.PRESENT}))
    service = _service(session, seed=3)

    for _ in range(25):
        next_card = service.next_card(profile.id)
        assert next_card is not None
        _, tense, _ = parse_card_key(next_card.card_key)
        assert tense is Tense.PRESENT


def test_practice_only_serves_enabled_verbs(session: Session):
    """The Verbs page's per-verb toggle (Part 4) must scope which verbs appear —
    a profile with only its default top-20 enabled never sees verb #200."""
    profiles = ProfileRepository(session)
    profile = profiles.create("narrow-deck")
    enablement = VerbEnablementRepository(session, default_enabled_count=20)
    enabled_ids = enablement.list_enabled_verb_ids(profile.id)
    assert len(enabled_ids) == 20

    service = _service(session, seed=11, enabled_verb_count=20)
    for _ in range(40):
        next_card = service.next_card(profile.id)
        assert next_card is not None
        verb_id, _, _ = parse_card_key(next_card.card_key)
        assert verb_id in enabled_ids
