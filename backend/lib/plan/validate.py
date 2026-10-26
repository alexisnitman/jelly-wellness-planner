"""Plan validation in code (CLAUDE.md rule 1): the model proposes, this module decides what is allowed.

An item is accepted only if it fits entirely inside ONE free window, inside waking hours, in the chosen week,
with a sensible length, a gap before and after, no overlap with another accepted item, within the per-day
limit, and (for recipes) no conflict with the user's diet or allergy notes. Everything else is rejected with a
reason; nothing invalid is ever returned as part of the plan.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo

from lib.plan import diet

MIN_MINUTES = 15
MIN_BY_KIND = {"wellness": 10}  # a stretch or breathing break can be short
MAX_MINUTES = {"workout": 150, "cooking": 180, "social": 300, "errand": 180, "rest": 360, "wellness": 90, "other": 240}
BUFFER_MINUTES = 15  # travel / change-over gap between items
MAX_ITEMS_PER_DAY = 4
BEDTIME_BUFFER_MINUTES = 60  # workouts must end this long before the waking hours end, so exercise doesn't eat into sleep
MAX_BUSY_MINUTES_PER_DAY = 300  # planned activity per day (rest and wellness breaks don't count): protects against overloading a day
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@dataclass
class Checked:
    ok: bool
    start: datetime | None = None
    end: datetime | None = None
    reasons: list[str] | None = None


def parse_times(day: date, start: str, end: str, tz: tzinfo) -> tuple[datetime, datetime] | None:
    ms, me = _HHMM.match(start or ""), _HHMM.match(end or "")
    if not ms or not me:
        return None
    s = datetime.combine(day, time(int(ms[1]), int(ms[2])), tzinfo=tz)
    e = datetime.combine(day, time(int(me[1]), int(me[2])), tzinfo=tz)
    return s, e


def _meal_ok(item: dict, tz: tzinfo, meal: str) -> bool:
    """A restaurant with no readable times: the meal must start in that meal's hours and have a sensible length."""
    from agents.restaurant_agent import MEALS  # the meal windows live with the finder

    earliest, latest, _, (lo, hi) = MEALS[meal]
    t = parse_times(item["day"], item["start"], item["end"], tz)
    return bool(t) and earliest.strftime("%H:%M") <= item["start"] <= latest.strftime("%H:%M") and lo <= (t[1] - t[0]).total_seconds() / 60 <= hi


def _movie_ok(item: dict, tz: tzinfo, where_kind: str) -> bool:
    """A movie with no readable showtime: start 12:00 to 21:30; a cinema outing 2 to 3.5 hours, at home 1 to 4 hours."""
    t = parse_times(item["day"], item["start"], item["end"], tz)
    lo, hi = (120, 210) if where_kind == "theater" else (60, 240)
    return bool(t) and "12:00" <= item["start"] <= "21:30" and lo <= (t[1] - t[0]).total_seconds() / 60 <= hi


def validate_items(
    items: list[dict],
    free: list[tuple[datetime, datetime]],
    week_first: date,
    week_days: int,
    wake_start: time,
    wake_end: time,
    tz: tzinfo,
    diet_notes: str = "",
    not_before: datetime | None = None,
    classes: dict[str, dict] | None = None,
    venues: dict[str, dict] | None = None,
    movies: dict[str, dict] | None = None,
) -> tuple[list[dict], list[dict]]:
    """Return (accepted, rejected). Items need: title, kind, day (date), start/end ("HH:MM"), optional recipe dict."""
    accepted: list[dict] = []
    rejected: list[dict] = []
    per_day: dict[date, int] = {}
    load: dict[date, int] = {}
    used_classes: set[str] = set()
    used_venues: set[str] = set()
    used_movies: set[str] = set()
    last_day = week_first + timedelta(days=week_days - 1)

    def reject(item: dict, *reasons: str) -> None:
        rejected.append({"item": item, "reasons": list(reasons)})

    def sort_key(i: dict):
        return (i["day"], i["start"])

    for item in sorted(items, key=sort_key):
        d: date = item["day"]
        cid = item.get("class_id")
        cls = (classes or {}).get(cid) if cid else None
        if cid:
            # a class must be one the class finder verified from the studio's own schedule, at its exact time
            if cls is None or item["kind"] != "workout":
                reject(item, "That class was not found on a studio schedule, so it can't be used.")
                continue
            if cid in used_classes:
                reject(item, "That class is already in the plan.")
                continue
            if (cls["day"], cls["start"], cls["end"]) != (item["day"], item["start"], item["end"]):
                reject(item, f"A class must use its real day and time ({cls['day']:%a} {cls['start']}-{cls['end']}).")
                continue
        vid = item.get("venue_id")
        venue = (venues or {}).get(vid) if vid else None
        if vid:
            # a restaurant must be one the restaurant finder read on a real page; a time it listed must be used exactly
            if venue is None or item["kind"] != "social":
                reject(item, "That restaurant was not found on a real page, so it can't be used.")
                continue
            if vid in used_venues:
                reject(item, "That restaurant is already in the plan.")
                continue
            if venue["slots"]:
                if not any((x["day"], x["start"], x["end"]) == (item["day"], item["start"], item["end"]) for x in venue["slots"]):
                    reject(item, "Use one of the reservation times read for this restaurant: " + ", ".join(f"{x['day']:%a} {x['start']}" for x in venue["slots"]) + ".")
                    continue
            elif not _meal_ok(item, tz, venue.get("meal", "dinner")):
                from agents.restaurant_agent import MEALS

                e_, l_, _, (lo_, hi_) = MEALS[venue.get("meal", "dinner")]
                reject(item, f"A {venue.get('meal', 'dinner')} should start between {e_:%H:%M} and {l_:%H:%M} and last {lo_} to {hi_} minutes.")
                continue
        mid = item.get("movie_id")
        movie = (movies or {}).get(mid) if mid else None
        if mid:
            # a movie must be one the movie finder read on a real page; a showtime it listed must be used exactly
            if movie is None or item["kind"] != "social":
                reject(item, "That movie was not found on a real page, so it can't be used.")
                continue
            if mid in used_movies:
                reject(item, "That movie is already in the plan.")
                continue
            if movie["slots"]:
                if not any((x["day"], x["start"], x["end"]) == (item["day"], item["start"], item["end"]) for x in movie["slots"]):
                    reject(item, "Use one of the showtimes read for this movie: " + ", ".join(f"{x['day']:%a} {x['start']}" for x in movie["slots"]) + ".")
                    continue
            elif not _movie_ok(item, tz, movie["where_kind"]):
                reject(item, "A movie night should start between 12:00 and 21:30 and last " + ("2 to 3.5 hours." if movie["where_kind"] == "theater" else "1 to 4 hours."))
                continue
        if not (week_first <= d <= last_day):
            reject(item, "That day is outside the chosen week.")
            continue
        times = parse_times(d, item["start"], item["end"], tz)
        if not times:
            reject(item, "Times must look like 07:30.")
            continue
        s, e = times
        minutes = int((e - s).total_seconds() // 60)
        floor = MIN_BY_KIND.get(item["kind"], MIN_MINUTES)
        if minutes < floor:
            reject(item, f"Too short (needs at least {floor} minutes, and the end must be after the start).")
            continue
        if not_before is not None and s < not_before:
            reject(item, "That time has already passed.")
            continue
        cap = MAX_MINUTES.get(item["kind"], 240)
        if minutes > cap:
            reject(item, f"Too long for a {item['kind']} item (max {cap} minutes).")
            continue
        if s < datetime.combine(d, wake_start, tzinfo=tz) or e > datetime.combine(d, wake_end, tzinfo=tz):
            reject(item, "Outside your waking hours.")
            continue
        if not any(ws <= s and e <= we for ws, we in free):
            reject(item, "Doesn't fit inside a free time window (it overlaps something on your calendar).")
            continue
        if item["kind"] == "workout" and e > datetime.combine(d, wake_end, tzinfo=tz) - timedelta(minutes=BEDTIME_BUFFER_MINUTES):
            reject(item, f"Too close to bedtime (finish workouts at least {BEDTIME_BUFFER_MINUTES} minutes before your waking hours end).")
            continue
        counts_toward_load = item["kind"] not in ("rest", "wellness")
        if counts_toward_load and load.get(d, 0) + minutes > MAX_BUSY_MINUTES_PER_DAY:
            reject(item, f"That would overload the day (more than {MAX_BUSY_MINUTES_PER_DAY // 60} hours planned). Spread things out.")
            continue
        clash = next((a for a in accepted if a["_s"] < e + timedelta(minutes=BUFFER_MINUTES) and s < a["_e"] + timedelta(minutes=BUFFER_MINUTES)), None)
        if clash:
            reject(item, f"Needs at least {BUFFER_MINUTES} minutes between items (clashes with '{clash['title']}').")
            continue
        if per_day.get(d, 0) >= MAX_ITEMS_PER_DAY:
            reject(item, f"Too many items on one day (max {MAX_ITEMS_PER_DAY}).")
            continue
        w = item.get("workout")
        if w is not None and item["kind"] == "workout" and not cid:
            main = w.get("main", [])
            if len(main) < 3 or sum(bool(re.search(r"\d", x)) for x in main) < 0.8 * len(main):
                reject(item, "Give at least 3 exercises in `main`, each with its sets and reps (or a time or distance) and rest, for example 'Pull-ups: 3 sets of 8 reps, rest 90 seconds'.")
                continue
        recipe = item.get("recipe")
        if recipe and diet_notes:
            conflicts = diet.recipe_conflicts(recipe.get("ingredients", []), diet_notes)
            if conflicts:
                reject(item, "Recipe conflicts with your diet or allergy notes: " + "; ".join(conflicts) + ".")
                continue
        per_day[d] = per_day.get(d, 0) + 1
        if counts_toward_load:
            load[d] = load.get(d, 0) + minutes
        entry = {**item, "_s": s, "_e": e}
        if cls:
            used_classes.add(cid)
            entry["class_info"] = {"studio": cls["studio"], "title": cls["title"], "url": cls["url"], "address": cls.get("address", ""), "length_assumed": bool(cls.get("length_assumed"))}
        if venue:
            used_venues.add(vid)
            entry["venue_info"] = {
                "name": venue["name"], "cuisine": venue.get("cuisine", ""), "address": venue.get("address", ""), "price": venue.get("price", ""),
                "url": venue["url"], "reservation_url": venue.get("reservation_url", ""), "style": venue.get("style", "reservation"), "meal": venue.get("meal", "dinner"), "availability": "read" if venue["slots"] else "unconfirmed",
            }
        if movie:
            used_movies.add(mid)
            entry["movie_info"] = {
                "title": movie["title"], "year": movie.get("year"), "genres": movie.get("genres", []), "blurb": movie.get("blurb", ""), "where": movie.get("where", ""),
                "where_kind": movie["where_kind"], "url": movie["url"], "watch_url": movie.get("watch_url", ""), "availability": "read" if movie["slots"] else "unconfirmed",
            }
        accepted.append(entry)
    out = []
    for a in sorted(accepted, key=lambda x: x["_s"]):
        a = dict(a)
        a["start_iso"], a["end_iso"] = a.pop("_s").isoformat(), a.pop("_e").isoformat()
        out.append(a)
    return out, rejected
