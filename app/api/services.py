"""SessionService — card selection / session logic, kept out of routes (§10, §12).

Routes call this; it talks to repositories and the pure domain (rendering,
card_gen, scheduler) and hands back plain domain-shaped values for the routes
to wrap in Pydantic schemas.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.orm import Session

from app.domain.card_gen import CardFront, card_front, generate_cards, parse_card_key
from app.domain.enums import Grade, Tense
from app.domain.models import Card, ReviewState
from app.domain.rendering import render
from app.domain.scheduler import Scheduler, Sm2Scheduler
from app.infra.repositories import (
    ProfileRepository,
    ReviewRepository,
    VerbEnablementRepository,
    VerbRepository,
)


@dataclass(frozen=True, slots=True)
class NextCard:
    """Everything a `GET /api/next` response needs (§12) — front metadata plus
    the already-rendered answer (the route includes both; the UI hides the
    answer client-side until tap, no second round trip)."""

    card_key: str
    front: CardFront
    answer: str


class SessionService:
    """Implements §10's selection rule, scoped to what the profile currently
    drills: due reviews first (ascending `due_date`), then a randomly-chosen new
    card, else nothing to show — restricted throughout to the profile's enabled
    tenses (Settings) and enabled verbs (Verbs page). There is no daily new-card
    cap (Part 2 — it made the deck look exhausted after ten cards). Also applies
    grades through the scheduler and persists the result."""

    def __init__(
        self,
        session: Session,
        *,
        scheduler: Scheduler | None = None,
        aux_present_only: bool = True,
        default_enabled_verb_count: int,
        rng: random.Random | None = None,
    ) -> None:
        self._verbs = VerbRepository(session)
        self._reviews = ReviewRepository(session)
        self._profiles = ProfileRepository(session)
        self._enablement = VerbEnablementRepository(
            session, default_enabled_count=default_enabled_verb_count
        )
        self._scheduler = scheduler or Sm2Scheduler()
        self._aux_present_only = aux_present_only
        self._rng = rng or random.Random()

    def next_card(self, profile_id: int, *, today: date | None = None) -> NextCard | None:
        if today is None:
            today = date.today()

        enabled_tenses, enabled_verb_ids = self._allowed(profile_id)

        due_cards = [
            card
            for card in (
                self._card_from_key(state.card_key)
                for state in self._reviews.list_due(profile_id, today)
            )
            if self._is_allowed(card, enabled_tenses, enabled_verb_ids)
        ]
        known = self._reviews.list_known_card_keys(profile_id)
        new_card = self._random_new_card(enabled_tenses, enabled_verb_ids, known)

        card = self._scheduler.pick_next(
            due_cards=due_cards, new_cards=[new_card] if new_card is not None else []
        )
        if card is None:
            return None
        return self._build_next_card(card)

    def grade_card(
        self, profile_id: int, card_key: str, grade: Grade, *, today: date | None = None
    ) -> None:
        if today is None:
            today = date.today()
        reviewed_at = datetime.combine(today, datetime.min.time())

        state = self._reviews.get(profile_id, card_key)
        if state is None:
            # First-ever grade for this card — the lazily-created starting state (§10).
            state = ReviewState(profile_id=profile_id, card_key=card_key, due_date=today)

        self._reviews.upsert(self._scheduler.grade(state, grade, today=today))
        self._reviews.log_grade(profile_id, card_key, grade, reviewed_at)

    def _allowed(self, profile_id: int) -> tuple[frozenset[Tense], frozenset[int]]:
        profile = self._profiles.get(profile_id)
        enabled_tenses = profile.enabled_tenses() if profile is not None else frozenset(Tense)
        enabled_verb_ids = self._enablement.list_enabled_verb_ids(profile_id)
        return enabled_tenses, enabled_verb_ids

    @staticmethod
    def _is_allowed(
        card: Card, enabled_tenses: frozenset[Tense], enabled_verb_ids: frozenset[int]
    ) -> bool:
        return card.tense in enabled_tenses and card.verb_id in enabled_verb_ids

    def _build_next_card(self, card: Card) -> NextCard:
        verb = self._verbs.get_by_id(card.verb_id)
        forms = self._verbs.get_forms(card.verb_id)
        aux = self._verbs.get_auxiliary_forms()
        return NextCard(
            card_key=card.card_key,
            front=card_front(verb, card),
            answer=render(verb, forms, card.tense, card.person, aux),
        )

    def _card_from_key(self, key: str) -> Card:
        verb_id, tense, person = parse_card_key(key)
        return Card(card_key=key, verb_id=verb_id, tense=tense, person=person)

    def _random_new_card(
        self,
        enabled_tenses: frozenset[Tense],
        enabled_verb_ids: frozenset[int],
        known: frozenset[str],
    ) -> Card | None:
        """Pick uniformly at random from every not-yet-introduced card across the
        enabled verbs/tenses (§1: "completely random in person, tense, and word").

        The full deck is at most ~2000 cards — trivial to materialize for a local
        single-machine app — so there's no need for `frequency_rank`-ordered
        walking, which is what made new-card introduction "feel scripted".
        """
        candidates = [
            card
            for verb in self._verbs.list_all()
            if verb.id in enabled_verb_ids
            for card in generate_cards(verb, aux_present_only=self._aux_present_only)
            if card.tense in enabled_tenses and card.card_key not in known
        ]
        return self._rng.choice(candidates) if candidates else None
