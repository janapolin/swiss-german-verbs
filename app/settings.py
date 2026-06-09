"""App-wide config, read from env with sane defaults (§15: "no magic numbers in
business logic"). Lives outside `domain` — pure domain code stays framework- and
env-free; this module is what infra/api/web read and pass *into* the domain as
plain arguments (e.g. `SessionService(aux_present_only=...)`).
"""

from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    return int(value) if value else default


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


# Whether auxiliaries (haa/sii/wèèrde) get present-tense cards only, vs the full
# present/perfect/future/konj2 set every other verb gets (§9, card_gen.py).
AUX_PRESENT_ONLY: bool = _bool_env("SWISSVERB_AUX_PRESENT_ONLY", True)

# The "Daily goal N / TARGET" counter on the practice screen's progress bar
# (§14 design reference) — counts grades submitted today, of any kind.
DAILY_GOAL_TARGET: int = _int_env("SWISSVERB_DAILY_GOAL_TARGET", 50)

# How many verbs (by `frequency_rank`, most-used first) a brand-new profile
# starts with enabled in its `verb_enablement` allow-list — the rest start
# disabled so a beginner isn't immediately drilled on obscure verbs.
DEFAULT_ENABLED_VERB_COUNT: int = _int_env("SWISSVERB_DEFAULT_ENABLED_VERB_COUNT", 20)
