"""Parse an .ics calendar into BUSY TIME RANGES ONLY.

Event titles, attendees, locations and descriptions are read by the parser but never copied into the
result, so nothing sensitive can leave this module (CLAUDE.md rule 2). Handles repeating events (RRULE),
time zones, floating times (read in the user's zone), all-day events, and respects status and
availability: cancelled events and events marked "free" (TRANSP:TRANSPARENT) don't block time.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo

import icalendar
import recurring_ical_events

MAX_EVENTS = 20000  # across the whole window read (up to 8 weeks)


class CalendarParseError(Exception):
    """Safe to show to the user."""


def _as_dt(value, tz: tzinfo, end_of_day: bool = False) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=tz) if value.tzinfo is None else value.astimezone(tz)
    # all-day (a date): the whole local day
    return datetime.combine(value, time.min, tzinfo=tz)


def merge(ranges: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    out: list[tuple[datetime, datetime]] = []
    for s, e in sorted(ranges):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def busy_ranges(ics_text: str, window_start: datetime, window_end: datetime, tz: tzinfo) -> tuple[list[tuple[datetime, datetime]], int]:
    """Busy ranges inside [window_start, window_end), merged, in `tz`. Also returns how many events were read."""
    try:
        cal = icalendar.Calendar.from_ical(ics_text)
    except Exception:
        raise CalendarParseError("That doesn't look like a calendar (.ics) file.")
    try:
        events = recurring_ical_events.of(cal).between(window_start, window_end)
    except Exception:
        raise CalendarParseError("Couldn't read the events in that calendar.")
    if len(events) > MAX_EVENTS:
        raise CalendarParseError("That calendar has too many events to read. Try a shorter range or a smaller calendar.")
    ranges: list[tuple[datetime, datetime]] = []
    for ev in events:
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        if str(ev.get("TRANSP", "OPAQUE")).upper() == "TRANSPARENT":
            continue  # marked "free" by the user
        try:
            start_raw, end_raw = ev.start, ev.end
        except Exception:
            continue
        start = _as_dt(start_raw, tz)
        end = _as_dt(end_raw, tz)
        if isinstance(end_raw, date) and not isinstance(end_raw, datetime) and end <= start:
            end = start + timedelta(days=1)
        if end <= start:
            continue
        s, e = max(start, window_start), min(end, window_end)
        if e > s:
            ranges.append((s, e))
    return merge(ranges), len(events)
