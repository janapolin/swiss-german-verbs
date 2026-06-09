"""Generate present-tense forms for regular verbs from their class (§13, grammar_rules.md §1).

The stem is the infinitive minus its trailing `-e` and, for separable verbs,
minus the leading prefix first. Endings are added per class; the result is
always *bare* (prefix-free) — exactly what `verb_forms` stores (§5).

    expand_present("mache", "A", None)        -> ("mache", "machsch", "macht", "mached")
    expand_present("uufhänke", "A", "uuf")     -> ("hänke", "hänksch", "hänkt", "hänked")
"""

from __future__ import annotations

from typing import Literal

VerbClass = Literal["A", "B", "C"]

# (sg1, sg2, sg3, pl) endings by class (grammar_rules.md §1).
_ENDINGS: dict[VerbClass, tuple[str, str, str, str]] = {
    "A": ("e", "sch", "t", "ed"),
    "B": ("e", "isch", "et", "ed"),
    "C": ("e", "isch", "t", "ed"),
}


def stem(infinitive: str, separable_prefix: str | None) -> str:
    """The conjugation stem: infinitive minus prefix (if any) minus trailing `-e`."""
    bare = infinitive.removeprefix(separable_prefix) if separable_prefix else infinitive
    if not bare.endswith("e"):
        raise ValueError(f"infinitive {infinitive!r} (bare {bare!r}) doesn't end in -e")
    return bare[:-1]


def expand_present(
    infinitive: str, verb_class: VerbClass, separable_prefix: str | None
) -> tuple[str, str, str, str]:
    """Return the bare `(present_sg1, present_sg2, present_sg3, present_pl)` forms."""
    s = stem(infinitive, separable_prefix)
    sg1, sg2, sg3, pl = _ENDINGS[verb_class]
    return (f"{s}{sg1}", f"{s}{sg2}", f"{s}{sg3}", f"{s}{pl}")
