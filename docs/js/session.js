/** Card selection logic (port of app/api/services.py + domain/card_gen.py). */

import { today } from './scheduler.js';
import { loadState } from './storage.js';

let _verbs = null;

export async function loadVerbs() {
  if (_verbs) return _verbs;
  const resp = await fetch('data/verbs.json');
  if (!resp.ok) throw new Error(`Failed to load verbs.json: ${resp.status}`);
  _verbs = await resp.json();
  return _verbs;
}

export function getVerbById(verbs, id) {
  return verbs.find(v => v.id === id) ?? null;
}

/** Initial settings for a brand-new profile: all 4 tenses, top-20 verbs enabled. */
export function defaultSettings(verbs) {
  return {
    tenses: ['present', 'perfect', 'future', 'konj2'],
    enabledVerbs: verbs.slice(0, 20).map(v => v.id),
  };
}

/**
 * Pick the next card to show for the given profile.
 * Returns an enriched card object, or null if there's nothing left to review.
 */
export function pickNextCard(profile, verbs, settings) {
  const todayStr = today();
  const enabledTenses = new Set(settings.tenses);
  const enabledVerbs = new Set(settings.enabledVerbs);

  const dueCards = [];
  const newCards = [];

  for (const verb of verbs) {
    if (!enabledVerbs.has(verb.id)) continue;
    for (const [cardKey, card] of Object.entries(verb.cards)) {
      if (!enabledTenses.has(card.tense)) continue;
      const enriched = { ...card, cardKey, verbId: verb.id, infinitive: verb.infinitive, gloss: verb.gloss };
      const state = loadState(profile, cardKey);
      if (!state) {
        newCards.push(enriched);
      } else if (state.dueDate <= todayStr) {
        dueCards.push({ card: enriched, dueDate: state.dueDate });
      }
    }
  }

  // Due reviews first, ascending by due date; then a random new card.
  if (dueCards.length > 0) {
    dueCards.sort((a, b) => a.dueDate.localeCompare(b.dueDate));
    return dueCards[0].card;
  }
  if (newCards.length > 0) {
    return newCards[Math.floor(Math.random() * newCards.length)];
  }
  return null;
}

/** Count cards reviewed today (from the log). */
export function countReviewsToday(profile) {
  const key = `swissverb:${profile}:log`;
  const log = JSON.parse(localStorage.getItem(key) ?? '[]');
  const t = today();
  return log.filter(e => e.reviewedAt.startsWith(t)).length;
}
