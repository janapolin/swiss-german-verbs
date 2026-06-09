"""Spelling normalisation — an ordered (pattern, replacement, position) table (§8).

The seed CSVs use two non-standard glyphs (confirmed against the raw bytes —
resolves the §17 "confirm exact codepoints" open item for *this* transcription):

- U+00E8 (`è`, LATIN SMALL LETTER E WITH GRAVE), doubled as `èè`:
  -> `ee` word-internal, `eh` word-final. "Final" means the digraph is the very
  last two characters of the word (`gèè` -> `geh`); anything followed by more
  letters, even just a trailing consonant, is internal (`wèèr` -> `weer`).
- U+022F (`ȯ`, LATIN SMALL LETTER O WITH DOT ABOVE): -> `ö`, applied per
  character — the source's doubled `ȯȯ` becomes doubled `öö`, matching the
  worked example `rȯȯtle -> röötle` (the rule's "-> ö" describes the glyph
  substitution, not a de-doubling).

Implemented as an ordered list of (pattern, replacement, position) rules per
§8's suggested shape — trivial to extend or correct as more glyphs surface.
"""

from __future__ import annotations

GRAVE_E = "è"
DOTTED_O = "ȯ"

_ANY = "any"
_INTERNAL = "internal"
_FINAL = "final"

# Ordered (pattern, replacement, position) rules, applied in sequence.
NORMALIZATION_RULES: tuple[tuple[str, str, str], ...] = (
    (DOTTED_O, "ö", _ANY),
    (GRAVE_E * 2, "ee", _INTERNAL),
    (GRAVE_E * 2, "eh", _FINAL),
)


def normalize(text: str) -> str:
    """Apply the ordered normalisation table to a single word/form (§8)."""
    for pattern, replacement, position in NORMALIZATION_RULES:
        text = _replace_at_position(text, pattern, replacement, position)
    return text


def _replace_at_position(text: str, pattern: str, replacement: str, position: str) -> str:
    pieces: list[str] = []
    i = 0
    while i < len(text):
        if text.startswith(pattern, i) and _matches_position(position, i, pattern, text):
            pieces.append(replacement)
            i += len(pattern)
        else:
            pieces.append(text[i])
            i += 1
    return "".join(pieces)


def _matches_position(position: str, index: int, pattern: str, text: str) -> bool:
    is_final = index + len(pattern) == len(text)
    if position == _ANY:
        return True
    if position == _FINAL:
        return is_final
    if position == _INTERNAL:
        return not is_final
    raise ValueError(f"unknown position: {position!r}")
