"""Free time = waking hours minus busy time, per day. Pure functions, no I/O, so they are easy to test."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, tzinfo

MIN_FREE_MINUTES = 30


def week_bounds(day: date, week_start: int) -> tuple[date, date]:
    """First day of the planning week (week_start: 0 = Monday) containing `day`, and the day after the last."""
    first = day - timedelta(days=(day.weekday() - week_start) % 7)
    return first, first + timedelta(days=7)


def free_windows(
    busy: list[tuple[datetime, datetime]],
    days: list[date],
    wake_start: time,
    wake_end: time,
    tz: tzinfo,
    min_minutes: int = MIN_FREE_MINUTES,
) -> list[tuple[datetime, datetime]]:
    """Free windows (at least `min_minutes`) inside each day's waking hours. `busy` must be merged and sorted."""
    out: list[tuple[datetime, datetime]] = []
    for d in days:
        cursor = datetime.combine(d, wake_start, tzinfo=tz)
        day_end = datetime.combine(d, wake_end, tzinfo=tz)
        for b_start, b_end in busy:
            if b_end <= cursor or b_start >= day_end:
                continue
            if b_start > cursor:
                out.append((cursor, b_start))
            cursor = max(cursor, b_end)
            if cursor >= day_end:
                break
        if cursor < day_end:
            out.append((cursor, day_end))
    return [(s, e) for s, e in out if (e - s) >= timedelta(minutes=min_minutes)]
