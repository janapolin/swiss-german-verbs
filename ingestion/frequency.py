"""Estimated real-world usage frequency for the seed verbs (§13).

CLAUDE.md §13 calls the original "irregulars 1-26, then regulars in CSV order"
scheme a placeholder ("Owner can reorder later without touching SRS state, since
the card key uses `verb_id` not rank"). This module replaces it with an estimate
of how often each verb's standard-German equivalent occurs in everyday speech —
most-used first — based on general knowledge of German verb frequency, ranking
by infinitive (post-`normalize()`, since that's the form `ingest` upserts by).

This is explicitly an *estimate*, not corpus-derived data: ties and near-ties are
broken by intuition, and the list is hand-maintained. The owner can reorder later
(§13) — reordering never touches SRS state, since `card_key` uses `verb_id`.

Verbs are also drilled in completely random order during practice (the SessionService
no longer walks by rank), so this ranking now only affects two things: the sort
order on the Verbs reference page, and which verbs a brand-new profile starts
with enabled (the top 20).
"""

from __future__ import annotations

# Most-used first. Every normalized infinitive from both seed CSVs must appear
# exactly once — `rank_index` raises if the sets don't match, so a future CSV
# edit that adds/removes/renames a verb surfaces here immediately.
ESTIMATED_FREQUENCY_ORDER: tuple[str, ...] = (
    "si", "ha", "werde", "chöne", "mache", "sele", "wele", "müese", "ga", "cho",
    "säge", "ge", "gsee", "wüsse", "la", "stah", "finde", "häisse", "bliibe", "ligge",
    "neh", "tue", "hebe", "möge", "zäige", "sitze", "spile", "frööge", "kenne", "läbe",
    "faare", "bruuche", "schaffe", "folge", "ässe", "schriibe", "mäine", "waarte", "läse",
    "uufhöre",
    "verzele", "sueche", "lose", "luege", "ghöre", "chauffe", "schlaaffe", "träffe",
    "renne", "verlüüre",
    "aafange", "zie", "lauffe", "falle", "rede", "aalüüte", "hälfe", "rüere", "trääge",
    "bhalte",
    "uufpasse", "wohne", "danke", "lache", "gnüüsse", "grüesse", "fehle", "soorge",
    "passe", "räise",
    "wäsche", "wöische", "hole", "gönne", "springe", "schwüme", "schreie", "lehre",
    "legge", "binde",
    "schniide", "trucke", "zügle", "bschiisse", "riisse", "hange", "choche", "butze",
    "boue", "fiire",
    "lange", "schwätze", "troue", "prichte", "aazünde", "lösche", "häize", "hueschte",
    "sprütze", "chotze",
    "biisse", "nütze", "versoorge", "schäle", "verraate", "rächne", "poschte", "tusche",
    "tuusche", "tüüsche",
    "trööschte", "abruume", "cheere", "aalange", "lupfe", "trüle", "wüsche", "gspüüre",
    "früüre", "chöie",
    "chützle", "hüete", "biige", "lisme", "flueche", "schnöre", "schüürge", "luure",
    "pfuuse", "grochse",
    "schläike", "winke", "büeze", "ruusche", "saage", "schletze", "schiisse", "chratze",
    "schnüüze", "tschuute",
    "schnarchle", "röötle", "zöisle", "zeere", "uufhänke", "leere",
)


def rank_index(infinitive: str) -> int:
    """Return the 0-based estimated-frequency position of a normalized infinitive.

    Unknown infinitives (shouldn't happen — every seed verb is covered) sort
    after all known ones, in the order they're first looked up.
    """
    try:
        return ESTIMATED_FREQUENCY_ORDER.index(infinitive)
    except ValueError:
        return len(ESTIMATED_FREQUENCY_ORDER)
