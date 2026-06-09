"""Server-rendered HTMX/Jinja routes (§3, §14): card front → reveal → grade,
profile picker, verb reference. Thin — delegate to `SessionService`/repositories;
this module's job is choosing templates and translating cookies/forms <-> calls.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app import settings
from app.api.services import NextCard, SessionService
from app.domain.card_gen import CORE_TENSES, card_key, parse_card_key
from app.domain.enums import Grade, Person, Tense
from app.domain.grammar import PERSON_LABELS, PRONOUNS, SEPARABLE_PREFIXES, TENSE_LABELS
from app.domain.models import Aux, Verb, VerbForms
from app.domain.rendering import render
from app.domain.scheduler import MAX_MASTERY_RATING, mastery_rating
from app.infra.db import get_session
from app.infra.repositories import (
    ProfileRepository,
    ReviewRepository,
    VerbEnablementRepository,
    VerbRepository,
)

router = APIRouter()

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=TEMPLATES_DIR)

PROFILE_COOKIE = "swissverb_profile_id"


def _active_profile_id(request: Request) -> int | None:
    raw = request.cookies.get(PROFILE_COOKIE)
    return int(raw) if raw and raw.isdigit() else None


def _tense_css_class(tense: Tense) -> str:
    return f"tense-{tense.value}"


def _card_context(next_card: NextCard | None) -> dict[str, Any]:
    """Template variables describing the current card — pulled into one place
    since both `/practice/card` and `/practice/grade` render the same partial."""
    if next_card is None:
        return {"card": None}
    _, tense, person = parse_card_key(next_card.card_key)
    return {
        "card": next_card,
        "tense_css_class": _tense_css_class(tense),
        "pronoun": PRONOUNS[person],
    }


def _session_service(session: Session) -> SessionService:
    return SessionService(
        session,
        aux_present_only=settings.AUX_PRESENT_ONLY,
        default_enabled_verb_count=settings.DEFAULT_ENABLED_VERB_COUNT,
    )


def _enablement_repo(session: Session) -> VerbEnablementRepository:
    return VerbEnablementRepository(
        session, default_enabled_count=settings.DEFAULT_ENABLED_VERB_COUNT
    )


# --- profile picker ----------------------------------------------------------


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)):
    profile_id = _active_profile_id(request)
    if profile_id is not None and ProfileRepository(session).get(profile_id) is not None:
        return RedirectResponse("/practice", status_code=303)
    return RedirectResponse("/profiles", status_code=303)


@router.get("/profiles", response_class=HTMLResponse)
def profile_picker(request: Request, session: Session = Depends(get_session)):
    profiles = ProfileRepository(session).list_all()
    return templates.TemplateResponse(request, "profile_picker.html", {"profiles": profiles})


@router.post("/profiles")
def create_profile(name: str = Form(...), session: Session = Depends(get_session)):
    profile = ProfileRepository(session).create(name.strip())
    response = RedirectResponse("/practice", status_code=303)
    response.set_cookie(PROFILE_COOKIE, str(profile.id), max_age=60 * 60 * 24 * 365)
    return response


@router.post("/profiles/{profile_id}/select")
def select_profile(profile_id: int, session: Session = Depends(get_session)):
    if ProfileRepository(session).get(profile_id) is None:
        return RedirectResponse("/profiles", status_code=303)
    response = RedirectResponse("/practice", status_code=303)
    response.set_cookie(PROFILE_COOKIE, str(profile_id), max_age=60 * 60 * 24 * 365)
    return response


@router.get("/profiles/{profile_id}/edit", response_class=HTMLResponse)
def edit_profile_form(
    request: Request,
    profile_id: int,
    confirm_delete: bool = False,
    session: Session = Depends(get_session),
):
    profile = ProfileRepository(session).get(profile_id)
    if profile is None:
        return RedirectResponse("/profiles", status_code=303)

    review_repo = ReviewRepository(session)
    today = date.today()
    stats = {
        "total_reviews": review_repo.count_reviews_total(profile_id),
        "reviews_today": review_repo.count_reviews_today(profile_id, today),
        "cards_seen": review_repo.count_cards_seen(profile_id),
        "member_since": profile.created_at.date(),
    }
    return templates.TemplateResponse(
        request,
        "profile_edit.html",
        {"profile": profile, "stats": stats, "confirm_delete": confirm_delete},
    )


@router.post("/profiles/{profile_id}/edit")
def rename_profile(profile_id: int, name: str = Form(""), session: Session = Depends(get_session)):
    profile_repo = ProfileRepository(session)
    if profile_repo.get(profile_id) is None:
        return RedirectResponse("/profiles", status_code=303)

    cleaned = name.strip()
    if cleaned:
        profile_repo.rename(profile_id, cleaned)
    return RedirectResponse(f"/profiles/{profile_id}/edit", status_code=303)


@router.post("/profiles/{profile_id}/delete")
def delete_profile(request: Request, profile_id: int, session: Session = Depends(get_session)):
    profile_repo = ProfileRepository(session)
    if profile_repo.get(profile_id) is not None:
        profile_repo.delete(profile_id)

    response = RedirectResponse("/profiles", status_code=303)
    if _active_profile_id(request) == profile_id:
        response.delete_cookie(PROFILE_COOKIE)
    return response


# --- settings ------------------------------------------------------------------

# Drilled in this fixed order everywhere a tense list is shown (matches §6's
# tense-pill ordering); `Tense.value` doubles as the toggle's form-field name.
SETTINGS_TENSES: tuple[Tense, ...] = (*CORE_TENSES, Tense.KONJ2)


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request, session: Session = Depends(get_session)):
    profile_id = _active_profile_id(request)
    profile = ProfileRepository(session).get(profile_id) if profile_id is not None else None
    if profile is None:
        return RedirectResponse("/profiles", status_code=303)

    enabled = profile.enabled_tenses()
    tense_toggles = [
        {"tense": tense, "label": TENSE_LABELS[tense], "checked": tense in enabled}
        for tense in SETTINGS_TENSES
    ]
    return templates.TemplateResponse(
        request, "settings.html", {"profile": profile, "tense_toggles": tense_toggles}
    )


@router.post("/settings")
def update_settings(
    request: Request,
    session: Session = Depends(get_session),
    present: str | None = Form(None),
    perfect: str | None = Form(None),
    future: str | None = Form(None),
    konj2: str | None = Form(None),
):
    profile_id = _active_profile_id(request)
    if profile_id is None or ProfileRepository(session).get(profile_id) is None:
        return RedirectResponse("/profiles", status_code=303)

    submitted = {
        Tense.PRESENT: present,
        Tense.PERFECT: perfect,
        Tense.FUTURE: future,
        Tense.KONJ2: konj2,
    }
    enabled = frozenset(tense for tense, value in submitted.items() if value is not None)
    ProfileRepository(session).set_tense_filters(profile_id, enabled)
    return RedirectResponse("/settings", status_code=303)


# --- practice screen ----------------------------------------------------------


@router.get("/practice", response_class=HTMLResponse)
def practice(request: Request, session: Session = Depends(get_session)):
    profile_id = _active_profile_id(request)
    if profile_id is None or ProfileRepository(session).get(profile_id) is None:
        return RedirectResponse("/profiles", status_code=303)

    reviews_today = ReviewRepository(session).count_reviews_today(profile_id, date.today())
    return templates.TemplateResponse(
        request,
        "practice.html",
        {
            "profile_id": profile_id,
            "reviews_today": reviews_today,
            "daily_goal_target": settings.DAILY_GOAL_TARGET,
        },
    )


@router.get("/practice/card", response_class=HTMLResponse)
def practice_card(request: Request, profile_id: int, session: Session = Depends(get_session)):
    next_card = _session_service(session).next_card(profile_id)
    return templates.TemplateResponse(
        request, "_card.html", {"profile_id": profile_id, **_card_context(next_card)}
    )


@router.post("/practice/grade", response_class=HTMLResponse)
def practice_grade(
    request: Request,
    profile_id: int = Form(...),
    card_key: str = Form(...),
    grade: Grade = Form(...),
    session: Session = Depends(get_session),
):
    service = _session_service(session)
    service.grade_card(profile_id, card_key, grade)
    next_card = service.next_card(profile_id)
    reviews_today = ReviewRepository(session).count_reviews_today(profile_id, date.today())

    return templates.TemplateResponse(
        request,
        "_card.html",
        {
            "profile_id": profile_id,
            "reviews_today": reviews_today,
            "daily_goal_target": settings.DAILY_GOAL_TARGET,
            "show_progress_oob": True,
            **_card_context(next_card),
        },
    )


# --- verb reference / management ----------------------------------------------

# Which verbs show up in the list — "enabled"/"disabled" reflect the active
# profile's per-verb allow-list (Part 4); `Tense.value`-style query string.
VERB_FILTERS: tuple[str, ...] = ("all", "enabled", "disabled")


def _require_active_profile(request: Request, session: Session) -> int | None:
    """Returns the active profile id, or `None` if the caller should redirect
    to `/profiles` (no active/valid profile — verb enablement is per-profile)."""
    profile_id = _active_profile_id(request)
    if profile_id is None or ProfileRepository(session).get(profile_id) is None:
        return None
    return profile_id


@router.get("/verbs", response_class=HTMLResponse)
def verb_list(request: Request, filter: str = "all", session: Session = Depends(get_session)):
    profile_id = _require_active_profile(request, session)
    if profile_id is None:
        return RedirectResponse("/profiles", status_code=303)
    if filter not in VERB_FILTERS:
        filter = "all"

    enabled_by_id = _enablement_repo(session).list_all(profile_id)
    rows = [
        {"verb": verb, "enabled": enabled_by_id.get(verb.id, False)}
        for verb in VerbRepository(session).list_all()
    ]
    if filter == "enabled":
        rows = [row for row in rows if row["enabled"]]
    elif filter == "disabled":
        rows = [row for row in rows if not row["enabled"]]

    return templates.TemplateResponse(
        request, "verbs.html", {"rows": rows, "active_filter": filter}
    )


@router.post("/verbs/{verb_id}/toggle", response_class=HTMLResponse)
def toggle_verb_enablement(
    request: Request,
    verb_id: int,
    filter: str = "all",
    session: Session = Depends(get_session),
):
    profile_id = _require_active_profile(request, session)
    if profile_id is None:
        return RedirectResponse("/profiles", status_code=303)
    if filter not in VERB_FILTERS:
        filter = "all"

    verb = VerbRepository(session).get_by_id(verb_id)
    if verb is None:
        return HTMLResponse("")

    enablement = _enablement_repo(session)
    currently_enabled = enablement.is_enabled(profile_id, verb_id)
    enabled = enablement.set_enabled(profile_id, verb_id, not currently_enabled)

    # If the row no longer matches the active filter, drop it from the list —
    # htmx swaps the `<li>`'s outerHTML, so an empty response removes it.
    if (filter == "enabled" and not enabled) or (filter == "disabled" and enabled):
        return HTMLResponse("")

    return templates.TemplateResponse(
        request,
        "_verb_row.html",
        {"row": {"verb": verb, "enabled": enabled}, "active_filter": filter},
    )


@router.post("/verbs/enable-all")
def enable_all_verbs(
    request: Request, filter: str = "all", session: Session = Depends(get_session)
):
    profile_id = _require_active_profile(request, session)
    if profile_id is None:
        return RedirectResponse("/profiles", status_code=303)
    _enablement_repo(session).set_all(profile_id, enabled=True)
    return RedirectResponse(f"/verbs?filter={filter}", status_code=303)


@router.post("/verbs/disable-all")
def disable_all_verbs(
    request: Request, filter: str = "all", session: Session = Depends(get_session)
):
    profile_id = _require_active_profile(request, session)
    if profile_id is None:
        return RedirectResponse("/profiles", status_code=303)
    _enablement_repo(session).set_all(profile_id, enabled=False)
    return RedirectResponse(f"/verbs?filter={filter}", status_code=303)


# --- add / edit verb (Part 5; shared form template, `is_edit` flag) -----------

_REQUIRED_VERB_FORM_FIELDS: tuple[tuple[str, str], ...] = (
    ("infinitive", "Infinitive"),
    ("english_gloss", "English meaning"),
    ("present_sg1", "Present tense — I …"),
    ("present_sg2", "Present tense — you …"),
    ("present_sg3", "Present tense — he/she/it …"),
    ("present_pl", "Present tense — we/you-all/they …"),
    ("participle", "Past participle"),
)
_REQUIRED_KONJ2_FORM_FIELDS: tuple[tuple[str, str], ...] = (
    ("konj2_sg1", "Would — I …"),
    ("konj2_sg2", "Would — you …"),
    ("konj2_sg3", "Would — he/she/it …"),
    ("konj2_pl", "Would — we/you-all/they …"),
)


def _detect_separable_prefix(infinitive: str) -> str | None:
    """Longest-prefix match against `SEPARABLE_PREFIXES` (§7) — duplicated from
    `ingestion.prefixes.detect_separable_prefix` rather than imported, since
    `ingestion/` is offline-only and never imported by the app (§3)."""
    for decorated in SEPARABLE_PREFIXES:
        prefix = decorated.removesuffix("-")
        if infinitive.startswith(prefix):
            return prefix
    return None


@dataclass(frozen=True, slots=True)
class _VerbFormInput:
    """A raw add/edit-verb submission: validates, derives the cleaned values
    `VerbRepository.create`/`update` need, and (being just data) doubles as the
    template context for re-displaying the form with the user's input intact
    when validation fails."""

    infinitive: str
    english_gloss: str
    separable_prefix_override: str
    aux: Aux
    present_sg1: str
    present_sg2: str
    present_sg3: str
    present_pl: str
    participle: str
    has_konj2: bool
    konj2_sg1: str
    konj2_sg2: str
    konj2_sg3: str
    konj2_pl: str
    notes: str

    def errors(self) -> list[str]:
        problems = [
            f"{label} is required."
            for field_name, label in _REQUIRED_VERB_FORM_FIELDS
            if not getattr(self, field_name).strip()
        ]
        if self.has_konj2:
            problems += [
                f"{label} is required (or uncheck the “would” form box)."
                for field_name, label in _REQUIRED_KONJ2_FORM_FIELDS
                if not getattr(self, field_name).strip()
            ]
        return problems

    def separable_prefix(self) -> str | None:
        override = self.separable_prefix_override.strip()
        return override if override else _detect_separable_prefix(self.infinitive.strip())

    def present_forms(self) -> tuple[str, str, str, str]:
        return (
            self.present_sg1.strip(),
            self.present_sg2.strip(),
            self.present_sg3.strip(),
            self.present_pl.strip(),
        )

    def konj2_forms(self) -> tuple[str, str, str, str] | None:
        if not self.has_konj2:
            return None
        return (
            self.konj2_sg1.strip(),
            self.konj2_sg2.strip(),
            self.konj2_sg3.strip(),
            self.konj2_pl.strip(),
        )


_BLANK_VERB_FORM = _VerbFormInput(
    infinitive="",
    english_gloss="",
    separable_prefix_override="",
    aux="ha",
    present_sg1="",
    present_sg2="",
    present_sg3="",
    present_pl="",
    participle="",
    has_konj2=False,
    konj2_sg1="",
    konj2_sg2="",
    konj2_sg3="",
    konj2_pl="",
    notes="",
)


def _verb_form_input_from(verb: Verb, forms: VerbForms) -> _VerbFormInput:
    return _VerbFormInput(
        infinitive=verb.infinitive,
        english_gloss=verb.english_gloss,
        separable_prefix_override=verb.separable_prefix or "",
        aux=verb.aux,
        present_sg1=forms.present_sg1,
        present_sg2=forms.present_sg2,
        present_sg3=forms.present_sg3,
        present_pl=forms.present_pl,
        participle=forms.participle,
        has_konj2=verb.has_konjunktiv2,
        konj2_sg1=forms.konj2_sg1 or "",
        konj2_sg2=forms.konj2_sg2 or "",
        konj2_sg3=forms.konj2_sg3 or "",
        konj2_pl=forms.konj2_pl or "",
        notes=verb.notes,
    )


@router.get("/verbs/new", response_class=HTMLResponse)
def new_verb_form(request: Request, session: Session = Depends(get_session)):
    if _require_active_profile(request, session) is None:
        return RedirectResponse("/profiles", status_code=303)
    return templates.TemplateResponse(
        request,
        "verb_form.html",
        {"is_edit": False, "verb": None, "values": _BLANK_VERB_FORM, "errors": []},
    )


@router.get("/verbs/{verb_id}/edit", response_class=HTMLResponse)
def edit_verb_form(request: Request, verb_id: int, session: Session = Depends(get_session)):
    if _require_active_profile(request, session) is None:
        return RedirectResponse("/profiles", status_code=303)
    repo = VerbRepository(session)
    verb = repo.get_by_id(verb_id)
    forms = repo.get_forms(verb_id) if verb is not None else None
    if verb is None or forms is None:
        return RedirectResponse("/verbs", status_code=303)
    return templates.TemplateResponse(
        request,
        "verb_form.html",
        {"is_edit": True, "verb": verb, "values": _verb_form_input_from(verb, forms), "errors": []},
    )


@router.post("/verbs/new", response_class=HTMLResponse)
def create_verb(
    request: Request,
    session: Session = Depends(get_session),
    infinitive: str = Form(""),
    english_gloss: str = Form(""),
    separable_prefix_override: str = Form(""),
    aux: Aux = Form(...),
    present_sg1: str = Form(""),
    present_sg2: str = Form(""),
    present_sg3: str = Form(""),
    present_pl: str = Form(""),
    participle: str = Form(""),
    has_konj2: bool = Form(False),
    konj2_sg1: str = Form(""),
    konj2_sg2: str = Form(""),
    konj2_sg3: str = Form(""),
    konj2_pl: str = Form(""),
    notes: str = Form(""),
):
    if _require_active_profile(request, session) is None:
        return RedirectResponse("/profiles", status_code=303)

    submission = _VerbFormInput(
        infinitive=infinitive,
        english_gloss=english_gloss,
        separable_prefix_override=separable_prefix_override,
        aux=aux,
        present_sg1=present_sg1,
        present_sg2=present_sg2,
        present_sg3=present_sg3,
        present_pl=present_pl,
        participle=participle,
        has_konj2=has_konj2,
        konj2_sg1=konj2_sg1,
        konj2_sg2=konj2_sg2,
        konj2_sg3=konj2_sg3,
        konj2_pl=konj2_pl,
        notes=notes,
    )
    errors = submission.errors()
    if errors:
        return templates.TemplateResponse(
            request,
            "verb_form.html",
            {"is_edit": False, "verb": None, "values": submission, "errors": errors},
            status_code=422,
        )

    verb = VerbRepository(session).create(
        infinitive=submission.infinitive.strip(),
        english_gloss=submission.english_gloss.strip(),
        aux=submission.aux,
        separable_prefix=submission.separable_prefix(),
        notes=submission.notes.strip(),
        present=submission.present_forms(),
        participle=submission.participle.strip(),
        konj2=submission.konj2_forms(),
    )
    return RedirectResponse(f"/verbs/{verb.id}", status_code=303)


@router.post("/verbs/{verb_id}/edit", response_class=HTMLResponse)
def update_verb(
    request: Request,
    verb_id: int,
    session: Session = Depends(get_session),
    infinitive: str = Form(""),
    english_gloss: str = Form(""),
    separable_prefix_override: str = Form(""),
    aux: Aux = Form(...),
    present_sg1: str = Form(""),
    present_sg2: str = Form(""),
    present_sg3: str = Form(""),
    present_pl: str = Form(""),
    participle: str = Form(""),
    has_konj2: bool = Form(False),
    konj2_sg1: str = Form(""),
    konj2_sg2: str = Form(""),
    konj2_sg3: str = Form(""),
    konj2_pl: str = Form(""),
    notes: str = Form(""),
):
    if _require_active_profile(request, session) is None:
        return RedirectResponse("/profiles", status_code=303)

    repo = VerbRepository(session)
    verb = repo.get_by_id(verb_id)
    if verb is None:
        return RedirectResponse("/verbs", status_code=303)

    submission = _VerbFormInput(
        infinitive=infinitive,
        english_gloss=english_gloss,
        separable_prefix_override=separable_prefix_override,
        aux=aux,
        present_sg1=present_sg1,
        present_sg2=present_sg2,
        present_sg3=present_sg3,
        present_pl=present_pl,
        participle=participle,
        has_konj2=has_konj2,
        konj2_sg1=konj2_sg1,
        konj2_sg2=konj2_sg2,
        konj2_sg3=konj2_sg3,
        konj2_pl=konj2_pl,
        notes=notes,
    )
    errors = submission.errors()
    if errors:
        return templates.TemplateResponse(
            request,
            "verb_form.html",
            {"is_edit": True, "verb": verb, "values": submission, "errors": errors},
            status_code=422,
        )

    updated = repo.update(
        verb_id,
        infinitive=submission.infinitive.strip(),
        english_gloss=submission.english_gloss.strip(),
        aux=submission.aux,
        separable_prefix=submission.separable_prefix(),
        notes=submission.notes.strip(),
        present=submission.present_forms(),
        participle=submission.participle.strip(),
        konj2=submission.konj2_forms(),
    )
    return RedirectResponse(f"/verbs/{updated.id}", status_code=303)


@router.get("/verbs/{verb_id}", response_class=HTMLResponse)
def verb_detail(request: Request, verb_id: int, session: Session = Depends(get_session)):
    repo = VerbRepository(session)
    verb = repo.get_by_id(verb_id)
    if verb is None:
        return RedirectResponse("/verbs", status_code=303)

    forms = repo.get_forms(verb.id)
    aux = repo.get_auxiliary_forms()
    tenses = (*CORE_TENSES, Tense.KONJ2) if verb.has_konjunktiv2 else CORE_TENSES
    persons = (Person.SG1, Person.SG2, Person.SG3, Person.PL)

    profile_id = _active_profile_id(request)
    ratings: dict[str, int] = {}
    if profile_id is not None:
        keys = [card_key(verb.id, tense, person) for tense in tenses for person in persons]
        states = ReviewRepository(session).get_many(profile_id, keys)
        ratings = {key: mastery_rating(states.get(key)) for key in keys}

    table = [
        {
            "tense_label": TENSE_LABELS[tense],
            "tense_css_class": _tense_css_class(tense),
            "rows": [
                {
                    "person_label": PERSON_LABELS[person],
                    "pronoun": PRONOUNS[person],
                    "answer": render(verb, forms, tense, person, aux),
                    "rating": ratings.get(card_key(verb.id, tense, person), 0),
                    "rating_range": range(MAX_MASTERY_RATING),
                }
                for person in persons
            ],
        }
        for tense in tenses
    ]
    return templates.TemplateResponse(request, "verb_detail.html", {"verb": verb, "table": table})
