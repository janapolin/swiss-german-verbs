"""Static linguistic vocabulary: pronouns, English labels, separable prefixes (§6, §7).

Pure data — no logic. The rendering engine looks these up; nothing here touches
a database or framework.
"""

from __future__ import annotations

from app.domain.enums import Person, Tense

# Zdt pronouns by person (§6 table). Configurable: a settings module may swap
# the plural pronoun (mir/ir/si all collapse to the same verb form) later.
PRONOUNS: dict[Person, str] = {
    Person.SG1: "ich",
    Person.SG2: "du",
    Person.SG3: "er",
    Person.PL: "mir",
}

# English glosses for the pronouns, shown alongside on the card front (§6 table).
PERSON_LABELS: dict[Person, str] = {
    Person.SG1: "I",
    Person.SG2: "you",
    Person.SG3: "he",
    Person.PL: "we",
}

# English labels for the tense pill on the card front (§6).
TENSE_LABELS: dict[Tense, str] = {
    Tense.PRESENT: "Present",
    Tense.PERFECT: "Past",
    Tense.FUTURE: "Future",
    Tense.KONJ2: "Would (Konj. II)",
}

# Separable prefixes, longest-first so "iine-" matches before "ii-" (§7, decided).
SEPARABLE_PREFIXES: tuple[str, ...] = (
    "iine-",
    "nache-",
    "zäme-",
    "dure-",
    "wäg-",
    "uuf-",
    "uus-",
    "zue-",
    "abe-",
    "ufe-",
    "aa-",
    "ab-",
    "ah-",
    "ii-",
    "um-",
    "uf-",
    "mit-",
    "vor-",
)

# Inseparable prefixes — never detach; participle takes no g- (§7, decided).
INSEPARABLE_PREFIXES: tuple[str, ...] = (
    "ver-",
    "be-",
    "ent-",
    "er-",
    "ge-",
    "zer-",
)
