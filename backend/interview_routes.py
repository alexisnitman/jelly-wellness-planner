"""Step 1 to 2 API. Login required (it spends model budget). The profile is read from the session on the
server, never from the request, and only yes/no flags and waking hours go to the model."""

from __future__ import annotations

import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from agents.interview_agent import run_interview
from auth import current_user
from lib.llm import AIUnavailable
from lib.roles import describe_role
from profile_routes import load_profile

router = APIRouter(prefix="/api/interview", tags=["interview"])
_CTRL_KEEP_NL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")


class QuestionsBody(BaseModel):
    description: str = Field(min_length=3, max_length=2000)

    @field_validator("description")
    @classmethod
    def clean(cls, v: str) -> str:
        v = _CTRL_KEEP_NL.sub("", v).strip()
        if len(v) < 3:
            raise ValueError("Describe your week in a few words")
        return v


class GoalOut(BaseModel):
    activity: str
    kind: Literal["workout", "cooking", "social", "errand", "rest", "wellness", "other"]
    times_per_week: int | None = None
    notes: str = ""


class QuestionOut(BaseModel):
    id: str
    text: str
    kind: Literal["single", "multi", "text"]
    options: list[str] = []
    why: str = ""


class QuestionsResult(BaseModel):
    goals: list[GoalOut]
    questions: list[QuestionOut]


@router.post("/questions", response_model=QuestionsResult)
async def questions(body: QuestionsBody, user: dict = Depends(current_user)) -> QuestionsResult:
    p = load_profile(user["id"])
    try:
        data = await run_interview(body.description, p.wake_start, p.wake_end, bool(p.city), bool(p.diet), bool(p.limits_note), describe_role(p.role, p.role_details))
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception:
        raise HTTPException(502, "Couldn't prepare your questions. Please try again in a moment.")  # never leak provider details
    return QuestionsResult(**data)
