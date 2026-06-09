"""Core vocabulary of the domain: Tense, Person, Grade (CLAUDE.md §4, §10)."""

from __future__ import annotations

from enum import StrEnum


class Tense(StrEnum):
    """The four tenses drilled by the app (CLAUDE.md §1, §4)."""

    PRESENT = "present"
    PERFECT = "perfect"
    FUTURE = "future"
    KONJ2 = "konj2"


class Person(StrEnum):
    """Grammatical persons. ``pl`` collapses 1./2./3. person — identical in Zdt (§4)."""

    SG1 = "sg1"
    SG2 = "sg2"
    SG3 = "sg3"
    PL = "pl"


class Grade(StrEnum):
    """Self-grade a learner gives a revealed card (§1, §10)."""

    HARD = "hard"
    GOOD = "good"
