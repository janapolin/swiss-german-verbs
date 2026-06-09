"""Tests for the SM-2 scheduler (§10).

§10 requires:
- hard reliably shortens interval vs good
- repeated good grades grow interval geometrically
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from app.domain.enums import Grade, Person, Tense
from app.domain.models import Card, ReviewState
from app.domain.scheduler import Sm2Scheduler, mastery_rating

CARD_KEY = "124:present:sg3"


def _state(**overrides: object) -> ReviewState:
    base = dict(
        profile_id=1,
        card_key=CARD_KEY,
        due_date=date(2026, 6, 1),
        ease_factor=2.5,
        interval_days=6,
        repetitions=2,
        lapses=0,
    )
    base.update(overrides)
    return ReviewState(**base)  # type: ignore[arg-type]


# --- hard reliably shortens interval vs good --------------------------------


def test_hard_shortens_interval_relative_to_good():
    scheduler = Sm2Scheduler()
    today = date(2026, 6, 7)
    established = _state()

    hard_next = scheduler.grade(established, Grade.HARD, today=today)
    good_next = scheduler.grade(established, Grade.GOOD, today=today)

    assert hard_next.interval_days < good_next.interval_days
    assert hard_next.due_date < good_next.due_date


def test_hard_resets_progress_and_lowers_ease():
    scheduler = Sm2Scheduler()
    today = date(2026, 6, 7)
    established = _state()

    hard_next = scheduler.grade(established, Grade.HARD, today=today)

    assert hard_next.interval_days == 1
    assert hard_next.repetitions == 0
    assert hard_next.lapses == established.lapses + 1
    assert hard_next.ease_factor < established.ease_factor
    assert hard_next.due_date == today + timedelta(days=1)
    assert hard_next.last_reviewed_at == today


def test_good_grows_progress_and_keeps_ease():
    scheduler = Sm2Scheduler()
    today = date(2026, 6, 7)
    established = _state()

    good_next = scheduler.grade(established, Grade.GOOD, today=today)

    assert good_next.repetitions == established.repetitions + 1
    assert good_next.lapses == established.lapses
    assert good_next.ease_factor == established.ease_factor  # quality 4 leaves EF unchanged
    assert good_next.interval_days == round(established.interval_days * established.ease_factor)
    assert good_next.due_date == today + timedelta(days=good_next.interval_days)


def test_ease_factor_never_drops_below_minimum():
    scheduler = Sm2Scheduler()
    today = date(2026, 6, 7)
    state = _state(ease_factor=1.35)

    next_state = scheduler.grade(state, Grade.HARD, today=today)

    assert next_state.ease_factor == pytest.approx(1.3)


# --- repeated good grades grow interval geometrically ------------------------


def test_repeated_good_grades_grow_interval_geometrically():
    scheduler = Sm2Scheduler()
    state = ReviewState(profile_id=1, card_key=CARD_KEY, due_date=date(2026, 1, 1))
    today = date(2026, 1, 1)

    intervals: list[int] = []
    for _ in range(6):
        state = scheduler.grade(state, Grade.GOOD, today=today)
        intervals.append(state.interval_days)
        today = state.due_date

    # 1 -> 6 -> round(6*2.5) -> ... : strictly growing, eventually by ~ease_factor each step.
    assert intervals == [1, 6, 15, 38, 95, 238]
    assert all(later > earlier for earlier, later in zip(intervals, intervals[1:], strict=False))
    for earlier, later in zip(intervals[2:], intervals[3:], strict=False):
        assert later / earlier == pytest.approx(state.ease_factor, abs=0.1)


# --- pick_next: §10 selection rule (due first, then new — no daily cap, §10/Part 2)

DUE_CARD = Card(card_key="1:present:sg1", verb_id=1, tense=Tense.PRESENT, person=Person.SG1)
NEW_CARD = Card(card_key="2:present:sg1", verb_id=2, tense=Tense.PRESENT, person=Person.SG1)


def test_pick_next_prefers_due_cards_over_new():
    scheduler = Sm2Scheduler()

    picked = scheduler.pick_next(due_cards=[DUE_CARD], new_cards=[NEW_CARD])

    assert picked == DUE_CARD


def test_pick_next_introduces_new_cards_when_nothing_due():
    scheduler = Sm2Scheduler()

    picked = scheduler.pick_next(due_cards=[], new_cards=[NEW_CARD])

    assert picked == NEW_CARD


def test_pick_next_returns_none_when_nothing_to_show():
    """No daily new-card cap (§10/Part 2 — it made the deck look exhausted after
    ten cards): `None` only happens when there's truly nothing left to show."""
    scheduler = Sm2Scheduler()

    picked = scheduler.pick_next(due_cards=[], new_cards=[])

    assert picked is None


# --- mastery_rating: 0-3 stars on the verb-detail page (Part 6) --------------


def test_mastery_rating_is_zero_when_never_seen():
    assert mastery_rating(None) == 0


def test_mastery_rating_is_one_when_struggling_or_freshly_lapsed():
    assert mastery_rating(_state(repetitions=0, lapses=0)) == 1
    assert mastery_rating(_state(repetitions=1, lapses=1)) == 1
    assert mastery_rating(_state(repetitions=2, lapses=3)) == 1


def test_mastery_rating_is_two_for_partial_progress():
    assert mastery_rating(_state(repetitions=1, lapses=0)) == 2
    assert mastery_rating(_state(repetitions=2, lapses=1)) == 2


def test_mastery_rating_is_three_when_solidly_known():
    assert mastery_rating(_state(repetitions=3, lapses=0)) == 3
    assert mastery_rating(_state(repetitions=5, lapses=1)) == 3
