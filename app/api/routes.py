"""API endpoints (§12). Thin: parse/validate via schemas, delegate to
`SessionService`/repositories, translate the result back. No business logic."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import settings
from app.api.schemas import (
    CardBackSchema,
    CardFrontSchema,
    CreateProfileRequest,
    GradeRequest,
    GradeResponse,
    NextCardResponse,
    ProfileResponse,
)
from app.api.services import SessionService
from app.infra.db import get_session
from app.infra.repositories import ProfileRepository

router = APIRouter(prefix="/api")


def _session_service(session: Session) -> SessionService:
    return SessionService(
        session,
        aux_present_only=settings.AUX_PRESENT_ONLY,
        default_enabled_verb_count=settings.DEFAULT_ENABLED_VERB_COUNT,
    )


@router.get("/next")
def get_next_card(
    profile_id: int, session: Session = Depends(get_session)
) -> NextCardResponse | None:
    next_card = _session_service(session).next_card(profile_id)
    if next_card is None:
        return None
    return NextCardResponse(
        card_key=next_card.card_key,
        front=CardFrontSchema(
            gloss=next_card.front.gloss,
            tense_label=next_card.front.tense_label,
            person_label=next_card.front.person_label,
            infinitive=next_card.front.infinitive,
        ),
        back=CardBackSchema(answer=next_card.answer),
    )


@router.post("/grade")
def grade_card(payload: GradeRequest, session: Session = Depends(get_session)) -> GradeResponse:
    _session_service(session).grade_card(payload.profile_id, payload.card_key, payload.grade)
    return GradeResponse()


@router.get("/profiles")
def list_profiles(session: Session = Depends(get_session)) -> list[ProfileResponse]:
    profiles = ProfileRepository(session).list_all()
    return [ProfileResponse(id=p.id, name=p.name, created_at=p.created_at) for p in profiles]


@router.post("/profiles")
def create_profile(
    payload: CreateProfileRequest, session: Session = Depends(get_session)
) -> ProfileResponse:
    profile = ProfileRepository(session).create(payload.name)
    return ProfileResponse(id=profile.id, name=profile.name, created_at=profile.created_at)
