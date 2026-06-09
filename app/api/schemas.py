"""Pydantic request/response models for the API (§12). Translation only — no
logic; routes assemble these from domain values returned by the services."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from app.domain.enums import Grade


class CardFrontSchema(BaseModel):
    gloss: str
    tense_label: str
    person_label: str
    infinitive: str


class CardBackSchema(BaseModel):
    answer: str


class NextCardResponse(BaseModel):
    card_key: str
    front: CardFrontSchema
    back: CardBackSchema


class GradeRequest(BaseModel):
    profile_id: int
    card_key: str
    grade: Grade


class GradeResponse(BaseModel):
    ok: bool = True


class ProfileResponse(BaseModel):
    id: int
    name: str
    created_at: datetime


class CreateProfileRequest(BaseModel):
    name: str
