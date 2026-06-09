"""Scheduler Protocol + Sm2Scheduler — a 3-button SM-2 variant (§10).

`grade` is a pure state transition: `(state, grade, today) -> new_state`. We add
an explicit `today` that §10's sketch omits — a pure function cannot call
`date.today()` itself and stay deterministic/testable, and `due_date` must be
computed from *some* reference date.

`pick_next` in §10 is sketched as `(profile_id, today) -> Card | None`, but
picking requires querying stored review state and content — that's `infra`
territory ("Card selection ... in a SessionService, not in the route", §10).
To keep the scheduler itself framework-free, `pick_next` here is the *pure*
selection rule over candidates the `SessionService` already fetched, filtered
to the profile's enabled tenses/verbs, and ordered (§10 step 1: due cards
ascending by `due_date`): first due card, else a new card, else nothing to show.
There is no daily new-card cap (v1 originally had one; it made the deck look
like it "ran out" after ten cards, which is exactly the bug we're fixing).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from datetime import date, timedelta
from typing import Protocol

from app.domain.enums import Grade
from app.domain.models import Card, ReviewState

DEFAULT_EASE_FACTOR = 2.5
MIN_EASE_FACTOR = 1.3

# SM-2 quality mapping for the app's 2-button self-grade (§10): hard -> 2, good -> 4.
_QUALITY: dict[Grade, int] = {Grade.HARD: 2, Grade.GOOD: 4}


class Scheduler(Protocol):
    def grade(self, state: ReviewState, grade: Grade, *, today: date) -> ReviewState: ...

    def pick_next(self, *, due_cards: Sequence[Card], new_cards: Sequence[Card]) -> Card | None: ...


class Sm2Scheduler:
    """3-button SM-2 variant — only `hard`/`good` grades exist (§1, §10)."""

    def grade(self, state: ReviewState, grade: Grade, *, today: date) -> ReviewState:
        """Apply a self-grade to `state`, returning the next `ReviewState`.

        - `hard` (quality 2): a lapse — repetitions reset to 0, ease drops,
          interval shrinks to 1 day. Returns soon (§10).
        - `good` (quality 4): normal SM-2 growth — ease unchanged, interval
          grows 1 -> 6 -> interval * ease_factor as repetitions accumulate.
        """
        quality = _QUALITY[grade]
        ease_factor = max(
            MIN_EASE_FACTOR,
            state.ease_factor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02)),
        )

        if quality < 3:
            interval_days = 1
            repetitions = 0
            lapses = state.lapses + 1
        else:
            repetitions = state.repetitions + 1
            if repetitions == 1:
                interval_days = 1
            elif repetitions == 2:
                interval_days = 6
            else:
                interval_days = round(state.interval_days * ease_factor)
            lapses = state.lapses

        return replace(
            state,
            ease_factor=ease_factor,
            interval_days=interval_days,
            repetitions=repetitions,
            lapses=lapses,
            due_date=today + timedelta(days=interval_days),
            last_reviewed_at=today,
        )

    def pick_next(self, *, due_cards: Sequence[Card], new_cards: Sequence[Card]) -> Card | None:
        """Pick the next card to show (§10 selection rule, minus the daily cap):
        a due review first, else a new card, else nothing left to show.

        Callers must pre-filter to the profile's enabled tenses/verbs and sort
        `due_cards` ascending by `due_date`; `new_cards` may contain at most one
        candidate (the `SessionService` already chose it — randomly, so the deck
        doesn't always introduce the same verb first).
        """
        if due_cards:
            return due_cards[0]
        if new_cards:
            return new_cards[0]
        return None


# Mastery rating (0-3) shown as stars on the verb-detail page — derived purely
# from `ReviewState`, no extra tracking needed:
#   0  no row at all                     -> never seen
#   1  repetitions == 0 or lapses >= repetitions -> struggling / just lapsed back to zero
#   2  0 < repetitions < 3               -> some good streaks, not yet solid
#   3  repetitions >= 3 and not lapsing  -> graded "Easy" enough times to be deep in the ladder
MAX_MASTERY_RATING = 3


def mastery_rating(state: ReviewState | None) -> int:
    """Map a card's `ReviewState` to a 0-3 mastery rating (stars, §10/verb detail)."""
    if state is None:
        return 0
    if state.repetitions == 0 or state.lapses >= state.repetitions:
        return 1
    if state.repetitions < MAX_MASTERY_RATING:
        return 2
    return 3
