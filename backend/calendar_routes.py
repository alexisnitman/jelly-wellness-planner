"""Calendar import (read-only). Returns busy and free TIME RANGES only, never event details.

Sources: an uploaded .ics (text sent from the browser; never stored), a pasted private link (optionally
remembered, encrypted), or the user's saved link. The saved link is never sent back to the browser.
"""

from __future__ import annotations

from pathlib import Path
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, model_validator

import crypto
import store
from auth import current_user
from lib.calendar import fetch, free_time, parse
from profile_routes import load_profile

router = APIRouter(prefix="/api/calendar", tags=["calendar"])


SAMPLE_ICS = Path(__file__).resolve().parent / "lib" / "calendar" / "sample.ics"


class ReadBody(BaseModel):
    source: Literal["file", "link", "saved", "sample"]
    ics_text: str | None = Field(default=None, max_length=3_000_000)
    url: str | None = Field(default=None, max_length=2000)
    remember: bool = False
    week_of: date | None = None  # any day in the first week to read; default today
    weeks: int = Field(default=6, ge=1, le=8)  # how many consecutive weeks to read (so the picker can move around)

    @model_validator(mode="after")
    def needs_input(self):
        if self.source == "file" and not (self.ics_text or "").strip():
            raise ValueError("Choose a calendar file")
        if self.source == "link" and not (self.url or "").strip():
            raise ValueError("Paste your calendar link")
        return self


class Span(BaseModel):
    start: str
    end: str


class FreeSpan(Span):
    minutes: int


class LinkStatus(BaseModel):
    saved: bool
    host: str = ""


class ReadResult(BaseModel):
    week_start: date  # first day of the first week read
    week_end: date  # last day of the last week read
    weeks: int
    timezone: str
    events_read: int
    busy: list[Span]
    free: list[FreeSpan]
    link: LinkStatus


def _link_status(user_id: int) -> LinkStatus:
    with store.connect() as conn:
        row = conn.execute("SELECT host FROM calendar_links WHERE user_id = ?", (user_id,)).fetchone()
    return LinkStatus(saved=row is not None, host=row["host"] if row else "")


@router.get("/link", response_model=LinkStatus)
def link_status(user: dict = Depends(current_user)) -> LinkStatus:
    return _link_status(user["id"])


@router.delete("/link", response_model=LinkStatus)
def forget_link(user: dict = Depends(current_user)) -> LinkStatus:
    with store.connect() as conn:
        conn.execute("DELETE FROM calendar_links WHERE user_id = ?", (user["id"],))
    return LinkStatus(saved=False)


@router.post("/read", response_model=ReadResult)
async def read_calendar(body: ReadBody, user: dict = Depends(current_user)) -> ReadResult:
    profile = load_profile(user["id"])
    if not profile.complete:
        raise HTTPException(409, "Save your profile first (waking hours and time zone).")
    tz = ZoneInfo(profile.timezone)

    link_to_remember: str | None = None
    try:
        if body.source == "file":
            text = body.ics_text or ""
        elif body.source == "sample":
            text = SAMPLE_ICS.read_text(encoding="utf-8")  # a made-up student week bundled with the app, so anyone can try it without a calendar
        else:
            if body.source == "saved":
                with store.connect() as conn:
                    row = conn.execute("SELECT url_enc FROM calendar_links WHERE user_id = ?", (user["id"],)).fetchone()
                url = crypto.decrypt(row["url_enc"]) if row else None
                if not url:
                    if row:  # unreadable (key changed): drop it and ask for the link again
                        with store.connect() as conn:
                            conn.execute("DELETE FROM calendar_links WHERE user_id = ?", (user["id"],))
                    raise HTTPException(409, "There's no saved link. Paste your calendar link.")
            else:
                url = fetch.normalize_link(body.url or "")
            text = await fetch.fetch_calendar_text(url)
            if body.source == "link" and body.remember:
                link_to_remember = url

        today = body.week_of or datetime.now(tz).date()
        first, _ = free_time.week_bounds(today, profile.week_start)
        after = first + timedelta(days=7 * body.weeks)
        w_start = datetime.combine(first, time.min, tzinfo=tz)
        w_end = datetime.combine(after, time.min, tzinfo=tz)
        busy, n_events = parse.busy_ranges(text, w_start, w_end, tz)
    except fetch.CalendarFetchError as exc:
        raise HTTPException(400, str(exc))
    except parse.CalendarParseError as exc:
        raise HTTPException(400, str(exc))

    if link_to_remember:  # only after the link has worked
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO calendar_links (user_id, url_enc, host) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET url_enc = excluded.url_enc, host = excluded.host, saved_at = datetime('now')",
                (user["id"], crypto.encrypt(link_to_remember), fetch.host_of(link_to_remember)),
            )

    h1, m1 = map(int, profile.wake_start.split(":"))
    h2, m2 = map(int, profile.wake_end.split(":"))
    days = [first + timedelta(days=i) for i in range(7 * body.weeks)]
    free = free_time.free_windows(busy, days, time(h1, m1), time(h2, m2), tz)
    return ReadResult(
        week_start=first,
        week_end=days[-1],
        weeks=body.weeks,
        timezone=profile.timezone,
        events_read=n_events,
        busy=[Span(start=s.isoformat(), end=e.isoformat()) for s, e in busy],
        free=[FreeSpan(start=s.isoformat(), end=e.isoformat(), minutes=int((e - s).total_seconds() // 60)) for s, e in free],
        link=_link_status(user["id"]),
    )
