"""The logged-in user's profile. There is no user id in the URL or body: the profile read or written is
always the one belonging to the session. Profile contents are never logged."""

from __future__ import annotations

import json
import re
from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator, model_validator

import store
from auth import current_user
from lib import roles

router = APIRouter(prefix="/api/profile", tags=["profile"])
_CTRL_KEEP_NL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class ProfileBody(BaseModel):
    wake_start: str = "07:00"
    wake_end: str = "22:00"
    week_start: int = Field(default=0, ge=0, le=6)  # 0 = Monday
    timezone: str = Field(default="UTC", max_length=64)
    city: str = Field(default="", max_length=80)
    diet: str = Field(default="", max_length=500)
    limits_note: str = Field(default="", max_length=500)
    complete: bool = False
    role: Literal["student", "professional", "other", ""] = ""
    role_details: dict[str, str] = Field(default_factory=dict, max_length=8)

    @field_validator("wake_start", "wake_end")
    @classmethod
    def hhmm(cls, v: str) -> str:
        if not _HHMM.match(v):
            raise ValueError("Use a time like 07:30")
        return v

    @field_validator("timezone")
    @classmethod
    def tz_ok(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError, OSError):
            raise ValueError("Unknown time zone")
        return v

    @field_validator("city", "diet", "limits_note")
    @classmethod
    def clean(cls, v: str) -> str:
        return _CTRL_KEEP_NL.sub("", v).strip()

    @model_validator(mode="after")
    def role_answers_match_the_role(self):
        self.role_details = roles.clean_details(self.role, self.role_details)  # drop answers that don't belong to this role or aren't valid choices
        return self

    @model_validator(mode="after")
    def hours_make_sense(self):
        h1, m1 = map(int, self.wake_start.split(":"))
        h2, m2 = map(int, self.wake_end.split(":"))
        if time(h2, m2) <= time(h1, m1):
            raise ValueError("Waking hours must end after they start (same day)")
        if (h2 * 60 + m2) - (h1 * 60 + m1) < 120:
            raise ValueError("Waking hours must span at least 2 hours")
        return self


def _row_to_body(row) -> ProfileBody:
    return ProfileBody(
        wake_start=row["wake_start"], wake_end=row["wake_end"], week_start=row["week_start"], timezone=row["timezone"],
        city=row["city"], diet=row["diet"], limits_note=row["limits_note"], complete=bool(row["complete"]),
        role=row["role"], role_details=json.loads(row["role_details"] or "{}"),
    )


def load_profile(user_id: int) -> ProfileBody:
    with store.connect() as conn:
        row = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
        if row is None:
            conn.execute("INSERT INTO profiles (user_id) VALUES (?)", (user_id,))
            row = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
    return _row_to_body(row)


class RoleQuestion(BaseModel):
    key: str
    question: str
    choices: list[str]  # empty = a short free-text answer


@router.get("/role-questions", response_model=dict[str, list[RoleQuestion]])
def role_questions() -> dict[str, list[RoleQuestion]]:
    """The follow-up questions for each role (the page renders these; the server validates answers against them)."""
    return {r: [RoleQuestion(key=k, question=q, choices=c) for k, q, c in qs] for r, qs in roles.ROLE_QUESTIONS.items()}


@router.get("", response_model=ProfileBody)
def get_profile(user: dict = Depends(current_user)) -> ProfileBody:
    return load_profile(user["id"])


@router.put("", response_model=ProfileBody)
def put_profile(body: ProfileBody, user: dict = Depends(current_user)) -> ProfileBody:
    load_profile(user["id"])  # make sure the row exists
    with store.connect() as conn:
        conn.execute(
            "UPDATE profiles SET wake_start=?, wake_end=?, week_start=?, timezone=?, city=?, diet=?, limits_note=?, role=?, role_details=?, complete=1, updated_at=datetime('now') WHERE user_id=?",
            (body.wake_start, body.wake_end, body.week_start, body.timezone, body.city, body.diet, body.limits_note, body.role, json.dumps(body.role_details), user["id"]),
        )
    return load_profile(user["id"])
