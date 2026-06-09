"""Separable-prefix detection by longest-prefix match (§7, §13 step 4).

`grammar.SEPARABLE_PREFIXES` is already ordered longest-first (so `iine-`
matches before `ii-`); the first hit wins.
"""

from __future__ import annotations

from app.domain.grammar import SEPARABLE_PREFIXES


def detect_separable_prefix(infinitive: str) -> tuple[str, str] | None:
    """Return `(prefix, bare_infinitive)` for the longest matching separable
    prefix, or `None` if `infinitive` doesn't start with one.
    """
    for decorated in SEPARABLE_PREFIXES:
        prefix = decorated.removesuffix("-")
        if infinitive.startswith(prefix):
            return prefix, infinitive.removeprefix(prefix)
    return None
