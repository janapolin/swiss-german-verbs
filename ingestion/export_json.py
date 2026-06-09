"""Offline script: read app.db, render all card answers, write docs/data/verbs.json.

Run after any change to the seed CSVs:
    python -m ingestion.ingest
    python -m ingestion.export_json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from app.domain.card_gen import card_front, generate_cards
from app.domain.grammar import PERSON_LABELS, PRONOUNS, TENSE_LABELS
from app.domain.rendering import render
from app.infra.db import engine
from app.infra.repositories import VerbRepository

OUT = Path(__file__).parent.parent / "docs" / "data" / "verbs.json"


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with Session(engine) as session:
        repo = VerbRepository(session)
        verbs = repo.list_all()
        aux = repo.get_auxiliary_forms()
        data = []
        for verb in verbs:
            forms = repo.get_forms(verb.id)
            if forms is None:
                continue
            cards: dict[str, object] = {}
            for card in generate_cards(verb):
                front = card_front(verb, card)
                answer = render(verb, forms, card.tense, card.person, aux)
                cards[card.card_key] = {
                    "tense": card.tense.value,
                    "person": card.person.value,
                    "tense_label": front.tense_label,
                    "person_label": PERSON_LABELS[card.person],
                    "pronoun": PRONOUNS[card.person],
                    "answer": answer,
                }
            data.append({
                "id": verb.id,
                "infinitive": verb.infinitive,
                "gloss": verb.english_gloss,
                "frequency_rank": verb.frequency_rank,
                "is_auxiliary": verb.is_auxiliary,
                "has_konjunktiv2": verb.has_konjunktiv2,
                "separable_prefix": verb.separable_prefix,
                "notes": verb.notes or "",
                "cards": cards,
            })

    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    total = sum(len(v["cards"]) for v in data)  # type: ignore[arg-type]
    print(f"Exported {len(data)} verbs, {total} cards → {OUT}")


if __name__ == "__main__":
    main()
