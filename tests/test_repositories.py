"""Tests for the repository methods added by Parts 4-7 (verb enablement,
verb CRUD, review-state batch lookups/stats, profile rename + cascade delete).

These exercise the ORM round trip directly against an in-memory DB seeded by
the real ingestion pipeline — `test_ingestion.py`/`test_services.py` already
cover content loading and session-level filtering, so this file focuses on the
repository methods themselves.
"""

from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domain.enums import Grade, Person, Tense
from app.domain.models import ReviewState
from app.domain.rendering import render
from app.infra.db import make_engine, make_session_factory
from app.infra.orm import Base, VerbEnablementRow
from app.infra.repositories import (
    ProfileRepository,
    ReviewRepository,
    VerbEnablementRepository,
    VerbRepository,
)
from ingestion.ingest import ingest


@pytest.fixture
def session() -> Session:
    engine = make_engine(":memory:")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        ingest(session)
        yield session


# --- VerbEnablementRepository (Part 4) ---------------------------------------


def test_verb_enablement_seeds_top_n_enabled_then_lists_all(session: Session):
    profiles = ProfileRepository(session)
    profile = profiles.create("enablement-tester")
    repo = VerbEnablementRepository(session, default_enabled_count=20)

    states = repo.list_all(profile.id)

    verbs_by_rank = sorted(VerbRepository(session).list_all(), key=lambda v: v.frequency_rank)
    top_20_ids = {v.id for v in verbs_by_rank[:20]}
    assert {verb_id for verb_id, enabled in states.items() if enabled} == top_20_ids
    assert repo.is_enabled(profile.id, verbs_by_rank[0].id) is True
    assert repo.is_enabled(profile.id, verbs_by_rank[-1].id) is False


def test_verb_enablement_set_enabled_toggles_a_single_verb(session: Session):
    profile = ProfileRepository(session).create("toggle-tester")
    repo = VerbEnablementRepository(session, default_enabled_count=20)
    verb_id = VerbRepository(session).list_all()[-1].id  # outside the default top-20

    assert repo.is_enabled(profile.id, verb_id) is False
    assert repo.set_enabled(profile.id, verb_id, True) is True
    assert repo.is_enabled(profile.id, verb_id) is True
    assert repo.set_enabled(profile.id, verb_id, False) is False
    assert repo.is_enabled(profile.id, verb_id) is False


def test_verb_enablement_set_all_bulk_flips_every_verb(session: Session):
    profile = ProfileRepository(session).create("bulk-tester")
    repo = VerbEnablementRepository(session, default_enabled_count=20)
    repo.list_all(profile.id)  # force lazy seeding before the bulk update

    repo.set_all(profile.id, enabled=True)
    assert all(repo.list_all(profile.id).values())

    repo.set_all(profile.id, enabled=False)
    assert not any(repo.list_all(profile.id).values())


# --- VerbRepository.create / update (Part 5) ---------------------------------


def test_create_verb_appends_at_end_of_frequency_ranking_and_renders(session: Session):
    repo = VerbRepository(session)
    max_rank_before = max(v.frequency_rank for v in repo.list_all())

    created = repo.create(
        infinitive="teste",
        english_gloss="to test",
        aux="ha",
        separable_prefix=None,
        notes="added in a test",
        present=("teste", "testisch", "testet", "tested"),
        participle="getestet",
        konj2=None,
    )

    assert created.frequency_rank == max_rank_before + 1
    assert created.verb_class is None
    assert created.has_konjunktiv2 is False

    forms = repo.get_forms(created.id)
    assert forms is not None
    aux_forms = repo.get_auxiliary_forms()
    assert render(created, forms, Tense.PRESENT, Person.SG3, aux_forms) == "er testet"


def test_update_verb_replaces_forms_and_can_remove_konjunktiv2(session: Session):
    repo = VerbRepository(session)
    created = repo.create(
        infinitive="probiere",
        english_gloss="to try",
        aux="ha",
        separable_prefix=None,
        notes="",
        present=("probiere", "probierisch", "probiert", "probiered"),
        participle="probiert",
        konj2=("probierti", "probiertisch", "probierti", "probierted"),
    )
    assert created.has_konjunktiv2 is True

    updated = repo.update(
        created.id,
        infinitive="probiere",
        english_gloss="to try out",
        aux="ha",
        separable_prefix=None,
        notes="edited",
        present=("probiere", "probierisch", "probiert", "probiered"),
        participle="probiert",
        konj2=None,
    )

    assert updated.english_gloss == "to try out"
    assert updated.has_konjunktiv2 is False
    forms = repo.get_forms(updated.id)
    assert forms is not None
    assert forms.konj2_sg1 is None


# --- ReviewRepository batch lookups + stats (Part 6/7) -----------------------


def test_get_many_returns_only_known_card_keys_for_the_profile(session: Session):
    profile = ProfileRepository(session).create("ratings-tester")
    repo = ReviewRepository(session)
    repo.upsert(
        ReviewState(profile_id=profile.id, card_key="1:present:sg1", due_date=date(2026, 6, 10))
    )
    repo.upsert(
        ReviewState(profile_id=profile.id, card_key="1:present:sg2", due_date=date(2026, 6, 12))
    )

    found = repo.get_many(profile.id, ["1:present:sg1", "1:present:sg2", "1:present:sg3"])

    assert set(found) == {"1:present:sg1", "1:present:sg2"}
    assert found["1:present:sg1"].due_date == date(2026, 6, 10)
    assert repo.get_many(profile.id, []) == {}


def test_review_stats_count_totals_today_and_cards_seen(session: Session):
    profile = ProfileRepository(session).create("stats-tester")
    repo = ReviewRepository(session)
    today = date(2026, 6, 8)
    yesterday = date(2026, 6, 7)

    repo.upsert(ReviewState(profile_id=profile.id, card_key="1:present:sg1", due_date=today))
    repo.upsert(ReviewState(profile_id=profile.id, card_key="1:present:sg2", due_date=today))
    repo.log_grade(profile.id, "1:present:sg1", Grade.GOOD, datetime(2026, 6, 8, 9, 0))
    repo.log_grade(profile.id, "1:present:sg1", Grade.HARD, datetime(2026, 6, 8, 10, 0))
    repo.log_grade(profile.id, "1:present:sg2", Grade.GOOD, datetime(2026, 6, 7, 9, 0))

    assert repo.count_reviews_total(profile.id) == 3
    assert repo.count_reviews_today(profile.id, today) == 2
    assert repo.count_reviews_today(profile.id, yesterday) == 1
    assert repo.count_cards_seen(profile.id) == 2


# --- ProfileRepository.rename / delete cascade (Part 7) ----------------------


def test_rename_profile_persists_the_new_name(session: Session):
    profiles = ProfileRepository(session)
    profile = profiles.create("old-name")

    renamed = profiles.rename(profile.id, "new-name")

    assert renamed.name == "new-name"
    assert profiles.get(profile.id).name == "new-name"


def test_delete_profile_cascades_user_state_rows(session: Session):
    profiles = ProfileRepository(session)
    profile = profiles.create("doomed")
    review_repo = ReviewRepository(session)
    review_repo.upsert(
        ReviewState(profile_id=profile.id, card_key="1:present:sg1", due_date=date(2026, 6, 10))
    )
    review_repo.log_grade(profile.id, "1:present:sg1", Grade.GOOD, datetime(2026, 6, 8, 9, 0))
    enablement = VerbEnablementRepository(session, default_enabled_count=20)
    enablement.set_enabled(profile.id, 1, True)

    profiles.delete(profile.id)

    assert profiles.get(profile.id) is None
    assert review_repo.get(profile.id, "1:present:sg1") is None
    assert review_repo.count_reviews_total(profile.id) == 0
    # Query the raw table directly — `list_all`/`is_enabled` would lazily
    # reseed rows for this (now-deleted) profile id, masking the cascade.
    remaining = session.scalars(
        select(VerbEnablementRow).where(VerbEnablementRow.profile_id == profile.id)
    ).all()
    assert remaining == []
