/** SM-2 spaced-repetition scheduler (port of app/domain/scheduler.py). */

const DEFAULT_EASE_FACTOR = 2.5;
const MIN_EASE_FACTOR = 1.3;

/** Returns today's local date as an ISO string YYYY-MM-DD. */
export function today() {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, '0');
  const day = String(d.getDate()).padStart(2, '0');
  return `${y}-${m}-${day}`;
}

function addDays(dateStr, n) {
  const [y, m, d] = dateStr.split('-').map(Number);
  const date = new Date(y, m - 1, d + n);
  const yr = date.getFullYear();
  const mo = String(date.getMonth() + 1).padStart(2, '0');
  const dy = String(date.getDate()).padStart(2, '0');
  return `${yr}-${mo}-${dy}`;
}

/**
 * Apply a grade to a review state, returning the next state object.
 * @param {object|null} state - existing review state, or null for a new card
 * @param {'hard'|'good'} gradeStr
 * @param {string} todayStr - ISO date YYYY-MM-DD
 */
export function gradeCard(state, gradeStr, todayStr) {
  const base = state ?? {
    easeFactor: DEFAULT_EASE_FACTOR,
    intervalDays: 0,
    repetitions: 0,
    lapses: 0,
  };

  const quality = gradeStr === 'hard' ? 2 : 4;
  const easeFactor = Math.max(
    MIN_EASE_FACTOR,
    base.easeFactor + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
  );

  let intervalDays, repetitions, lapses;
  if (quality < 3) {
    intervalDays = 1;
    repetitions = 0;
    lapses = base.lapses + 1;
  } else {
    repetitions = base.repetitions + 1;
    if (repetitions === 1) intervalDays = 1;
    else if (repetitions === 2) intervalDays = 6;
    else intervalDays = Math.round(base.intervalDays * easeFactor);
    lapses = base.lapses;
  }

  return {
    easeFactor,
    intervalDays,
    repetitions,
    lapses,
    dueDate: addDays(todayStr, intervalDays),
    lastReviewedAt: todayStr,
  };
}

/**
 * Map a card's state to a 0-3 mastery star rating.
 * @param {object|null} state
 */
export function masteryRating(state) {
  if (!state) return 0;
  if (state.repetitions === 0 || state.lapses >= state.repetitions) return 1;
  if (state.repetitions < 3) return 2;
  return 3;
}
