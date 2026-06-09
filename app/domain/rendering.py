"""The rendering engine — the linguistic core (§6). Pure; no I/O.

`render(verb, forms, tense, person, aux)` returns the back of a card: the
fully assembled "pronoun + conjugated form[ + detached prefix]" string.

Note on the signature: §6 sketches it as `render(verb, tense, person)`, but the
engine "depends on the present-tense tables of three auxiliaries loaded from
the DB by infinitive at startup" to assemble perfect/future cells. Pure domain
code cannot reach into a database, so those tables are passed in explicitly via
`forms` (this verb's own stored forms) and `aux` (haa/sii/wèèrde's). A future
`SessionService` is responsible for fetching both via the repositories before
calling in.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.enums import Person, Tense
from app.domain.grammar import PRONOUNS
from app.domain.models import Verb, VerbForms

# Infinitives of the three auxiliaries the engine needs present-tense tables for
# (§6, §9) — spelled as they're *stored* in the seed CSVs (no `èè`/`ȯȯ` glyphs in
# any of these three, so normalization is a no-op and the stored spelling matches).
HAA_INFINITIVE = "ha"
SII_INFINITIVE = "si"
WERDE_INFINITIVE = "werde"


@dataclass(frozen=True, slots=True)
class AuxiliaryForms:
    """Present-tense conjugation tables for `haa`, `sii`, and `wèèrde` (§6, §9).

    `haa`/`sii` supply the perfect auxiliary; `werde` supplies the future
    auxiliary for every verb (including itself — `er wird wèèrde`).
    """

    haa: VerbForms
    sii: VerbForms
    werde: VerbForms

    def perfect_auxiliary(self, verb: Verb) -> VerbForms:
        return self.haa if verb.aux == "ha" else self.sii


def render(verb: Verb, forms: VerbForms, tense: Tense, person: Person, aux: AuxiliaryForms) -> str:
    """Render the back of a card: pronoun + conjugated form (§6)."""
    override = forms.overrides.get((tense, person))
    if override is not None:
        return override

    pronoun = PRONOUNS[person]

    if tense is Tense.PRESENT:
        return _render_present(verb, forms, pronoun, person)
    if tense is Tense.PERFECT:
        return _render_perfect(verb, forms, pronoun, person, aux)
    if tense is Tense.FUTURE:
        return _render_future(verb, pronoun, person, aux)
    if tense is Tense.KONJ2:
        return _render_konj2(verb, forms, pronoun, person)

    raise AssertionError(f"unhandled tense: {tense!r}")


def _render_present(verb: Verb, forms: VerbForms, pronoun: str, person: Person) -> str:
    form = forms.present(person)
    if verb.separable_prefix:
        return f"{pronoun} {form} {verb.separable_prefix}"
    return f"{pronoun} {form}"


def _render_perfect(
    verb: Verb, forms: VerbForms, pronoun: str, person: Person, aux: AuxiliaryForms
) -> str:
    aux_form = aux.perfect_auxiliary(verb).present(person)
    participle_full = (
        f"{verb.separable_prefix}{forms.participle}" if verb.separable_prefix else forms.participle
    )
    return f"{pronoun} {aux_form} {participle_full}"


def _render_future(verb: Verb, pronoun: str, person: Person, aux: AuxiliaryForms) -> str:
    werde_form = aux.werde.present(person)
    return f"{pronoun} {werde_form} {verb.infinitive}"


def _render_konj2(verb: Verb, forms: VerbForms, pronoun: str, person: Person) -> str:
    if not verb.has_konjunktiv2:
        raise ValueError(f"{verb.infinitive!r} has no Konjunktiv II — card_gen must not emit it")
    form = forms.konj2(person)
    if form is None:
        raise ValueError(f"{verb.infinitive!r} is missing a konj2 form for {person.value}")
    if verb.separable_prefix:
        return f"{pronoun} {form} {verb.separable_prefix}"
    return f"{pronoun} {form}"
