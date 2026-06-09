"""Tests for the ingestion pipeline (§13): runs the real CLI pipeline against
the real seed CSVs into a throwaway in-memory DB, then checks the loaded
content through the same repositories the app uses.
"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from app.domain.enums import Person, Tense
from app.domain.rendering import render
from app.infra.db import make_engine, make_session_factory
from app.infra.orm import Base
from app.infra.repositories import VerbRepository
from ingestion.ingest import ingest


@pytest.fixture
def session() -> Session:
    engine = make_engine(":memory:")
    Base.metadata.create_all(engine)
    with make_session_factory(engine)() as session:
        yield session


def test_ingest_loads_every_seed_row_exactly_once(session: Session):
    count = ingest(session)

    repo = VerbRepository(session)
    verbs = repo.list_all()
    assert count == 146
    assert len(verbs) == 146
    assert len({verb.infinitive for verb in verbs}) == 146  # no infinitive collisions


def test_ingest_is_idempotent(session: Session):
    first = ingest(session)
    second = ingest(session)

    assert first == second == 146
    assert len(VerbRepository(session).list_all()) == 146


def test_frequency_rank_is_a_stable_permutation_with_common_verbs_first(session: Session):
    """`frequency_rank` (§13) now reflects estimated real-world usage frequency
    (`ingestion.frequency`) rather than "irregulars first" — it must still be a
    dense 1..146 permutation (so `list_all()`/new-profile defaults work), and the
    handful of universally-common verbs should land near the top of the deck."""
    ingest(session)

    verbs = VerbRepository(session).list_all()
    assert sorted(verb.frequency_rank for verb in verbs) == list(range(1, 147))

    by_infinitive = {verb.infinitive: verb.frequency_rank for verb in verbs}
    for common in ("si", "ha", "werde", "mache", "ga", "cho"):
        assert by_infinitive[common] <= 20, f"{common!r} should rank in the top 20"


def test_ingest_is_idempotent_about_frequency_rank(session: Session):
    """Re-running ingestion must not reshuffle ranks — they're derived purely
    from the (stable) curated frequency order, so a rerun is a no-op for ranking."""
    ingest(session)
    first = {v.infinitive: v.frequency_rank for v in VerbRepository(session).list_all()}

    ingest(session)
    second = {v.infinitive: v.frequency_rank for v in VerbRepository(session).list_all()}

    assert first == second


def test_normalization_applied_to_stored_forms(session: Session):
    """No seed infinitive contains the raw `èè` digraph anymore, but several
    *stored forms* still do (`werde.present_pl` raw `wèèrded`, `fehle`/`leere`'s
    participles raw `gfèèlt`/`glèèrt`) and must land normalized — `weerded`/
    `gfeelt`/`gleert` — per §8 (internal `èè` -> `ee`)."""
    ingest(session)

    repo = VerbRepository(session)
    werde = repo.get_by_infinitive("werde")
    assert werde is not None
    werde_forms = repo.get_forms(werde.id)
    assert werde_forms is not None
    assert werde_forms.present_pl == "weerded"

    fehle = repo.get_by_infinitive("fehle")
    assert fehle is not None
    fehle_forms = repo.get_forms(fehle.id)
    assert fehle_forms is not None
    assert fehle_forms.participle == "gfeelt"

    leere = repo.get_by_infinitive("leere")
    assert leere is not None
    leere_forms = repo.get_forms(leere.id)
    assert leere_forms is not None
    assert leere_forms.participle == "gleert"


def test_separable_prefix_detected_and_stripped_to_bare_forms(session: Session):
    ingest(session)

    repo = VerbRepository(session)
    verb = repo.get_by_infinitive("uufhänke")
    forms = repo.get_forms(verb.id)

    assert verb.separable_prefix == "uuf"
    assert forms.present_sg3 == "hänkt"  # bare — prefix stripped
    assert forms.participle == "ghänkt"  # bare — prefix stripped


def test_loaded_verb_renders_correctly_end_to_end(session: Session):
    """Smoke-tests that ingestion produces exactly the bare/normalized shape
    the rendering engine (§6) expects — including the auxiliary tables."""
    ingest(session)

    repo = VerbRepository(session)
    aux = repo.get_auxiliary_forms()

    mache = repo.get_by_infinitive("mache")
    forms = repo.get_forms(mache.id)
    assert render(mache, forms, Tense.PRESENT, Person.SG3, aux) == "er macht"
    assert render(mache, forms, Tense.PERFECT, Person.SG3, aux) == "er het gmacht"
    assert render(mache, forms, Tense.FUTURE, Person.SG3, aux) == "er wird mache"

    uufhanke = repo.get_by_infinitive("uufhänke")
    forms = repo.get_forms(uufhanke.id)
    assert render(uufhanke, forms, Tense.PRESENT, Person.SG3, aux) == "er hänkt uuf"
    assert render(uufhanke, forms, Tense.PERFECT, Person.SG3, aux) == "er het uufghänkt"


def test_lehre_and_leere_are_distinct_verbs(session: Session):
    """`lehre` ("to teach") and `lèère`/`leere` ("to empty") are distinct
    lexical items that would collide post-normalization under their original
    seed spellings (both -> infinitive `leere`, participle `gleert`); the seed
    CSV spells the former `lehre` precisely so they stay distinct."""
    ingest(session)

    repo = VerbRepository(session)
    lehre = repo.get_by_infinitive("lehre")
    leere = repo.get_by_infinitive("leere")

    assert lehre is not None and leere is not None
    assert lehre.id != leere.id
    assert lehre.english_gloss == "to teach"
    assert leere.english_gloss == "to empty"
    assert repo.get_forms(lehre.id).participle == "glehrt"
    assert repo.get_forms(leere.id).participle == "gleert"
