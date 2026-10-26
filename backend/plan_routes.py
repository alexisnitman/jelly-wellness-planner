"""Step 4 API: propose a plan. Login required (spends model budget).

The client sends the FREE windows it got from /api/calendar/read for the chosen week (or nothing, meaning "assume
I'm free during my waking hours"). The server re-checks and clips them to the week and the user's waking hours, and
the profile notes are read from the session, never from the request. Busy time and event details never reach here.
"""

from __future__ import annotations

import asyncio
import re
import time as _time
from datetime import date, datetime, time, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field, field_validator

from agents import class_agent, movie_agent, restaurant_agent
from agents.class_agent import run_class_search, search_classes
from agents.movie_agent import run_movie_search, search_movies
from agents.restaurant_agent import run_restaurant_search, search_restaurants
from agents.planner_agent import run_planner
from auth import current_user
from search_cache import PersistentCache
from lib.analysis_text import clean_line
from lib.calendar import free_time
from lib import evidence
from lib.llm import AIUnavailable
from lib.roles import describe_role
from lib.plan import ics, validate
from profile_routes import load_profile

router = APIRouter(prefix="/api/plan", tags=["plan"])
_CTRL_KEEP_NL = re.compile(r"[\x00-\x09\x0b-\x1f\x7f]")
DISCLAIMER = "Workout and meal ideas are general suggestions, not medical advice. Check anything that doesn't suit you with a professional."


def _clean(v: str, n: int) -> str:
    return _CTRL_KEEP_NL.sub("", v).strip()[:n]


class GoalIn(BaseModel):
    activity: str = Field(max_length=80)
    kind: Literal["workout", "cooking", "social", "errand", "rest", "wellness", "other"] = "other"
    times_per_week: int | None = Field(default=None, ge=0, le=14)
    notes: str = Field(default="", max_length=200)


class AnswerIn(BaseModel):
    question: str = Field(max_length=160)
    answer: str = Field(max_length=400)


class SpanIn(BaseModel):
    start: datetime
    end: datetime


class ClassRequestIn(BaseModel):
    """The user's choice on the form: some workouts should be real classes, at a studio they name or somewhere new."""

    mode: Literal["studio", "new"]
    studio: str = Field(default="", max_length=80)
    types: list[str] = Field(default_factory=list, max_length=6)
    count: int = Field(ge=1, le=7)
    city: str = Field(default="", max_length=80)  # overrides the profile city for this search


class DinnerRequestIn(BaseModel):
    """The user's choice on the form: some get-togethers are meals out (breakfast, brunch, lunch or dinner) at a real restaurant (named, or suggested)."""

    count: int = Field(ge=1, le=5)
    meal: Literal["breakfast", "brunch", "lunch", "dinner"] = "dinner"
    style: Literal["reservation", "walk_in"] = "reservation"  # a restaurant with a booking site, or a walk-in place
    party: int = Field(default=2, ge=1, le=12)
    cuisines: list[str] = Field(default_factory=list, max_length=4)
    named: str = Field(default="", max_length=80)  # a restaurant the user already has in mind
    city: str = Field(default="", max_length=80)  # overrides the profile city for this search


class MovieRequestIn(BaseModel):
    """The user's choice on the form: some get-togethers are movie nights, in a theater or at home, in certain genres."""

    count: int = Field(ge=1, le=3)
    where: Literal["theater", "home"]
    genres: list[str] = Field(default_factory=list, max_length=3)
    city: str = Field(default="", max_length=80)  # overrides the profile city for this search


class CurrentItem(BaseModel):
    title: str = Field(max_length=80)
    kind: Literal["workout", "cooking", "social", "errand", "rest", "wellness", "other"] = "other"
    day: date
    start: str = Field(max_length=5)
    end: str = Field(max_length=5)


class ProposeBody(BaseModel):
    description: str = Field(min_length=3, max_length=2000)
    goals: list[GoalIn] = Field(default_factory=list, max_length=12)
    answers: list[AnswerIn] = Field(default_factory=list, max_length=10)
    week_start: date
    free: list[SpanIn] | None = Field(default=None, max_length=600)  # None = no calendar: assume free in waking hours
    # a revision: what the user wants changed in the plan they have seen
    feedback: str = Field(default="", max_length=600)
    current: list[CurrentItem] = Field(default_factory=list, max_length=40)
    removed: list[str] = Field(default_factory=list, max_length=20)
    class_request: ClassRequestIn | None = None
    dinner_request: DinnerRequestIn | None = None
    movie_request: MovieRequestIn | None = None
    ingredients: list[str] = Field(default_factory=list, max_length=8)  # ingredients the user wants in their recipes
    priorities: list[str] = Field(default_factory=list, max_length=3)  # what the user most wants from their routine

    @field_validator("ingredients")
    @classmethod
    def clean_ingredients(cls, v: list[str]) -> list[str]:
        return list(dict.fromkeys(x for x in (clean_line(i, 40) for i in v) if x))[:8]

    @field_validator("priorities")
    @classmethod
    def known_priorities(cls, v: list[str]) -> list[str]:
        return [p for p in dict.fromkeys(v) if p in evidence.PRIORITIES]

    @field_validator("description")
    @classmethod
    def desc(cls, v: str) -> str:
        v = _CTRL_KEEP_NL.sub("", v).strip()
        if len(v) < 3:
            raise ValueError("Describe your week in a few words")
        return v


class RecipeOut(BaseModel):
    servings: int
    prep_minutes: int
    cook_minutes: int
    ingredients: list[str]
    steps: list[str]


class WorkoutOut(BaseModel):
    intensity: Literal["easy", "moderate", "hard"]
    equipment: list[str]
    warmup: list[str]
    main: list[str]
    cooldown: list[str]
    adaptation_note: str


class ClassInfoOut(BaseModel):
    studio: str
    title: str
    url: str
    address: str = ""
    length_assumed: bool = False


class StudioOut(BaseModel):
    name: str
    url: str = ""
    readable: bool = False


class UnreadableOut(BaseModel):
    name: str
    url: str = ""
    reason: str = ""


class ClassSearchOut(BaseModel):
    requested: int
    found: int  # real classes that fit the user's free time
    studios_checked: list[StudioOut] = []
    unreadable: list[UnreadableOut] = []
    note: str = ""
    checked: str = ""  # date the schedules were read


class VenueInfoOut(BaseModel):
    name: str
    cuisine: str = ""
    address: str = ""
    price: str = ""
    url: str  # the page the restaurant was read from
    reservation_url: str = ""  # where the user checks availability and books (Jelly Wellness Planner never books)
    style: Literal["reservation", "walk_in"] = "reservation"
    meal: Literal["breakfast", "brunch", "lunch", "dinner"] = "dinner"
    availability: Literal["read", "unconfirmed"]  # "read" = this time was listed on the page when it was read


class RestaurantOut(BaseModel):
    """One recommended restaurant, with its booking link (or, for walk-in places, its own page)."""

    name: str
    cuisine: str = ""
    address: str = ""
    price: str = ""
    url: str  # the page it was read from
    reservation_url: str = ""
    has_times: bool = False
    walk_in_confirmed: bool = False  # the page itself says no reservations (otherwise: no booking site was found)


class DinnerSearchOut(BaseModel):
    meal: Literal["breakfast", "brunch", "lunch", "dinner"] = "dinner"
    style: Literal["reservation", "walk_in"] = "reservation"
    restaurants: list[RestaurantOut] = []
    requested: int
    found: int  # real restaurants read from a page
    with_times: int  # of those, how many had a reservation time that fits the user's free time
    unreadable: list[UnreadableOut] = []
    note: str = ""
    checked: str = ""


class MovieInfoOut(BaseModel):
    title: str
    year: int | None = None
    genres: list[str] = []
    blurb: str = ""
    where: str = ""  # the theater or the streaming service, only if the page named it
    where_kind: Literal["theater", "home"]
    url: str  # the page it was read from
    watch_url: str = ""
    availability: Literal["read", "unconfirmed"]  # "read" = this showtime was listed on the page when it was read


class MovieOut(BaseModel):
    title: str
    year: int | None = None
    genres: list[str] = []
    blurb: str = ""
    where: str = ""
    url: str
    watch_url: str = ""
    has_times: bool = False


class MovieSearchOut(BaseModel):
    where: Literal["theater", "home"]
    movies: list[MovieOut] = []
    requested: int
    found: int
    unreadable: list[UnreadableOut] = []
    note: str = ""
    checked: str = ""


class EvidenceOut(BaseModel):
    topic: str
    quote: str
    source: str
    url: str
    checked: str


class BenefitOut(BaseModel):
    lead: str
    goal_link: str = ""
    evidence: list[EvidenceOut]


class ItemOut(BaseModel):
    id: str
    title: str
    kind: Literal["workout", "cooking", "social", "errand", "rest", "wellness", "other"]
    goal: str
    day: str
    start: str
    end: str
    start_iso: str
    end_iso: str
    why: str
    notes: str
    recipe: RecipeOut | None = None
    workout: WorkoutOut | None = None
    class_id: str | None = None
    class_info: ClassInfoOut | None = None
    venue_id: str | None = None
    venue_info: VenueInfoOut | None = None
    movie_id: str | None = None
    movie_info: MovieInfoOut | None = None
    evidence_ids: list[str] = []
    goal_link: str = ""
    benefit: BenefitOut | None = None


class UnplacedOut(BaseModel):
    title: str
    reason: str


class PlanResult(BaseModel):
    week_start: str
    items: list[ItemOut]
    unplaced: list[UnplacedOut]
    summary: str
    used_calendar: bool
    class_search: ClassSearchOut | None = None
    dinner_search: DinnerSearchOut | None = None
    movie_search: MovieSearchOut | None = None
    disclaimer: str = DISCLAIMER


def _now(tz) -> datetime:
    return datetime.now(tz)  # a function so tests can pin the clock


def _drop_past(free: list[tuple[datetime, datetime]], now: datetime) -> list[tuple[datetime, datetime]]:
    """Nothing can be planned in the past: remove free time before now (and trim a window that has already started)."""
    out = []
    for a, b in free:
        a = max(a, now)
        if b - a >= timedelta(minutes=free_time.MIN_FREE_MINUTES):
            out.append((a, b))
    return out


def _free_windows(spans_in: list[SpanIn] | None, day_list: list[date], h1: int, m1: int, h2: int, m2: int, tz) -> list[tuple[datetime, datetime]]:
    """Free windows for the week, with the past removed. None = no calendar (free during waking hours). Client windows are clipped to waking hours."""
    return _drop_past(_free_windows_all(spans_in, day_list, h1, m1, h2, m2, tz), _now(tz))


def _free_windows_all(spans_in: list[SpanIn] | None, day_list: list[date], h1: int, m1: int, h2: int, m2: int, tz) -> list[tuple[datetime, datetime]]:
    if spans_in is None:
        return free_time.free_windows([], day_list, time(h1, m1), time(h2, m2), tz)
    spans = []
    for s in spans_in:
        a = s.start.astimezone(tz) if s.start.tzinfo else s.start.replace(tzinfo=tz)
        b = s.end.astimezone(tz) if s.end.tzinfo else s.end.replace(tzinfo=tz)
        if b > a:
            spans.append((a, b))
    free = []
    for d in day_list:
        lo, hi = datetime.combine(d, time(h1, m1), tzinfo=tz), datetime.combine(d, time(h2, m2), tzinfo=tz)
        for a, b in sorted(spans):
            s2, e2 = max(a, lo), min(b, hi)
            if e2 - s2 >= timedelta(minutes=free_time.MIN_FREE_MINUTES):
                free.append((s2, e2))
    return free


# Verified classes per (user, week): a revision reuses them instead of searching again, and export checks class items
# against them, so a class can only come from what the class finder really read (never from the browser's say-so).
_CLASS_TTL = 6 * 3600
_class_cache = PersistentCache("class", ClassSearchOut)  # in the database, so a server restart doesn't lose it


def _class_sig(req: ClassRequestIn, city: str) -> tuple:
    return (req.mode, req.studio.strip().lower(), tuple(sorted(t.lower() for t in req.types)), city.strip().lower())


def _cached_classes(user_id: int, week: date) -> dict | None:
    hit = _class_cache.get((user_id, week))
    if hit and _time.time() - hit["at"] < _CLASS_TTL:
        return hit
    _class_cache.pop((user_id, week), None)
    return None


# Same idea for restaurants: per (user, week), reused by revisions and by export (which only accepts venues found here).
_venue_cache = PersistentCache("venue", DinnerSearchOut)


def _dinner_sig(req: DinnerRequestIn, city: str) -> tuple:
    return (req.named.strip().lower(), tuple(sorted(c.lower() for c in req.cuisines)), req.party, req.style, req.meal, city.strip().lower())


def _cached_venues(user_id: int, week: date) -> dict | None:
    hit = _venue_cache.get((user_id, week))
    if hit and _time.time() - hit["at"] < _CLASS_TTL:
        return hit
    _venue_cache.pop((user_id, week), None)
    return None


# And for movies.
_movie_cache = PersistentCache("movie", MovieSearchOut)


def _movie_sig(req: MovieRequestIn, city: str) -> tuple:
    return (req.where, tuple(sorted(g.lower() for g in req.genres)), city.strip().lower() if req.where == "theater" else "")


def _cached_movies(user_id: int, week: date) -> dict | None:
    hit = _movie_cache.get((user_id, week))
    if hit and _time.time() - hit["at"] < _CLASS_TTL:
        return hit
    _movie_cache.pop((user_id, week), None)
    return None


# Searches started early. The slow part of a class, meal or movie search (the model reading web pages) doesn't need the
# user's calendar, so the page starts it as soon as the user finishes describing their week; by the time they reach the
# plan step it is usually done. Only the quick code check against their free time is left. Keyed by (user, kind, week).
_prefetch: dict[tuple[int, str, date], dict] = {}


def _start_prefetch(user_id: int, kind: str, week: date, sig: tuple, make) -> None:
    hit = _prefetch.get((user_id, kind, week))
    if hit and hit["sig"] == sig and _time.time() - hit["at"] < _CLASS_TTL:
        return  # already running or finished for this request
    task = asyncio.ensure_future(make())
    task.add_done_callback(lambda t: t.cancelled() or t.exception())  # mark any error as seen; propose falls back to a normal search
    _prefetch[(user_id, kind, week)] = {"at": _time.time(), "sig": sig, "task": task}


async def _take_prefetch(user_id: int, kind: str, week: date, sig: tuple) -> dict | None:
    """The finished (or still running) early search for exactly this request, or None. AI limits still apply."""
    hit = _prefetch.pop((user_id, kind, week), None)
    if not hit or hit["sig"] != sig or _time.time() - hit["at"] >= _CLASS_TTL:
        return None
    try:
        return await hit["task"]
    except AIUnavailable:
        raise
    except Exception:
        return None


def _revision(body: ProposeBody) -> dict | None:
    """The user's change request plus the plan they were looking at, cleaned to single lines (it is data for the model)."""
    feedback = _CTRL_KEEP_NL.sub("", body.feedback).strip()
    if not (feedback or body.current or body.removed):
        return None
    return {
        "feedback": feedback,
        "current": [{"title": clean_line(c.title, 80), "kind": c.kind, "day": c.day.isoformat(), "start": c.start, "end": c.end} for c in body.current],
        "removed": [t for t in (clean_line(r, 80) for r in body.removed) if t],
    }


@router.post("/propose", response_model=PlanResult)
async def propose(body: ProposeBody, user: dict = Depends(current_user)) -> PlanResult:
    p = load_profile(user["id"])
    if not p.complete:
        raise HTTPException(409, "Save your profile first (waking hours and time zone).")
    tz = ZoneInfo(p.timezone)
    first, _ = free_time.week_bounds(body.week_start, p.week_start)
    if first != body.week_start:
        raise HTTPException(400, "Pick the first day of a week.")
    days = 7
    h1, m1 = map(int, p.wake_start.split(":"))
    h2, m2 = map(int, p.wake_end.split(":"))
    day_list = [first + timedelta(days=i) for i in range(days)]

    free = _free_windows(body.free, day_list, h1, m1, h2, m2, tz)

    classes: list[dict] | None = None
    class_req: dict | None = None
    class_out: ClassSearchOut | None = None
    async def _find_classes() -> None:
        nonlocal classes, class_req, class_out
        if body.class_request:
            cr = body.class_request
            city = _clean(cr.city, 80) or _clean(p.city, 80)
            class_req = {"mode": cr.mode, "studio": clean_line(cr.studio, 80), "types": [t for t in (clean_line(x, 40) for x in cr.types) if t], "count": cr.count}
            checked = date.today().isoformat()
            if not city:
                classes = []
                class_out = ClassSearchOut(requested=cr.count, found=0, note="Add your city in Profile so I can find classes near you.", checked=checked)
            else:
                sig = _class_sig(cr, city)
                hit = _cached_classes(user["id"], first)
                if hit and hit["sig"] == sig:
                    classes, class_out = hit["classes"], hit["out"]
                else:
                    try:
                        raw = await _take_prefetch(user["id"], "class", first, sig)
                        found = class_agent.verify_search(raw, first, days, tz, free, _now(tz)) if raw else await run_class_search(city, cr.mode, class_req["studio"], class_req["types"], first, days, tz, free, _now(tz))
                        classes = found["classes"]
                        c = found["counts"]
                        note = ""
                        if not classes:
                            note = "I couldn't read any classes that fit your free time." + (" Some schedules are drawn by scripts I can't read; open the links below." if found["unreadable"] else "")
                        elif c["outside_free"]:
                            note = f"{c['outside_free']} other class times didn't fit your free time."
                        class_out = ClassSearchOut(requested=cr.count, found=len(classes), studios_checked=[StudioOut(**x) for x in found["studios_checked"]], unreadable=[UnreadableOut(**x) for x in found["unreadable"]], note=note, checked=checked)
                    except AIUnavailable as exc:
                        raise HTTPException(503, str(exc))
                    except Exception:
                        classes = []
                        class_out = ClassSearchOut(requested=cr.count, found=0, note="The class search failed, so no classes were scheduled. Try again in a moment.", checked=checked)
                    _class_cache[(user["id"], first)] = {"at": _time.time(), "sig": sig, "classes": classes, "out": class_out}

    venues: list[dict] | None = None
    dinner_req: dict | None = None
    dinner_out: DinnerSearchOut | None = None
    async def _find_dinner() -> None:
        nonlocal venues, dinner_req, dinner_out
        if body.dinner_request:
            dr = body.dinner_request
            city = _clean(dr.city, 80) or _clean(p.city, 80)
            dinner_req = {"count": dr.count, "meal": dr.meal, "style": dr.style, "party": dr.party, "named": clean_line(dr.named, 80), "cuisines": [c for c in (clean_line(x, 40) for x in dr.cuisines) if c]}
            checked = date.today().isoformat()
            if not city:
                venues = []
                dinner_out = DinnerSearchOut(meal=dr.meal, style=dr.style, requested=dr.count, found=0, with_times=0, note="Add your city in Profile so I can find restaurants near you.", checked=checked)
            else:
                sig = _dinner_sig(dr, city)
                hit = _cached_venues(user["id"], first)
                if hit and hit["sig"] == sig:
                    venues, dinner_out = hit["venues"], hit["out"]
                else:
                    try:
                        raw = await _take_prefetch(user["id"], "dinner", first, sig)
                        found = restaurant_agent.verify_search(raw, first, days, tz, free, _now(tz)) if raw else await run_restaurant_search(city, dinner_req["named"], dinner_req["cuisines"], dr.party, first, days, tz, free, _now(tz), style=dr.style, meal=dr.meal)
                        venues = found["restaurants"]
                        with_times = sum(1 for v in venues if v["slots"])
                        if not venues:
                            note = "I couldn't find restaurants I could read that " + ("take reservations." if dr.style == "reservation" else "are walk-in.") + " Try naming a restaurant, or search for one directly."
                        elif dr.style == "walk_in":
                            note = "No booking site was found for these places, so they look like walk-ins (some pages say so outright). Some may still take bookings, and hours and waits aren't checked: open their page or call before you go."
                        elif not with_times:
                            note = "None of these sites show open tables in a form I can read (booking widgets usually hide them). Use the links to check availability and book; nothing is reserved."
                        else:
                            note = "Times marked as read were listed on the page when I looked; they can be gone by now."
                        dinner_out = DinnerSearchOut(meal=dr.meal, style=dr.style, restaurants=[RestaurantOut(name=v["name"], cuisine=v["cuisine"], address=v["address"], price=v["price"], url=v["url"], reservation_url=v["reservation_url"], has_times=bool(v["slots"]), walk_in_confirmed=bool(v.get("walk_in_confirmed"))) for v in venues], requested=dr.count, found=len(venues), with_times=with_times, unreadable=[UnreadableOut(**x) for x in found["unreadable"]], note=note, checked=checked)
                    except AIUnavailable as exc:
                        raise HTTPException(503, str(exc))
                    except Exception:
                        venues = []
                        dinner_out = DinnerSearchOut(meal=dr.meal, style=dr.style, requested=dr.count, found=0, with_times=0, note="The restaurant search failed, so no dinners were scheduled. Try again in a moment.", checked=checked)
                    _venue_cache[(user["id"], first)] = {"at": _time.time(), "sig": sig, "venues": venues, "out": dinner_out}

    movies: list[dict] | None = None
    movie_req: dict | None = None
    movie_out: MovieSearchOut | None = None
    async def _find_movies() -> None:
        nonlocal movies, movie_req, movie_out
        if body.movie_request:
            mr = body.movie_request
            city = _clean(mr.city, 80) or _clean(p.city, 80)
            movie_req = {"count": mr.count, "where": mr.where, "genres": [g for g in (clean_line(x, 30) for x in mr.genres) if g]}
            checked = date.today().isoformat()
            if mr.where == "theater" and not city:
                movies = []
                movie_out = MovieSearchOut(where=mr.where, requested=mr.count, found=0, note="Add your city in Profile so I can find what's playing near you.", checked=checked)
            else:
                sig = _movie_sig(mr, city)
                hit = _cached_movies(user["id"], first)
                if hit and hit["sig"] == sig:
                    movies, movie_out = hit["movies"], hit["out"]
                else:
                    try:
                        raw = await _take_prefetch(user["id"], "movie", first, sig)
                        found = movie_agent.verify_search(raw, first, days, tz, free, _now(tz)) if raw else await run_movie_search(city, mr.where, movie_req["genres"], first, days, tz, free, _now(tz))
                        movies = found["movies"]
                        with_times = sum(1 for m in movies if m["slots"])
                        if not movies:
                            note = "I couldn't read any " + ("showtime" if mr.where == "theater" else "movie") + " pages. Try a theater's own site or your streaming services."
                        elif mr.where == "theater":
                            note = ("Times marked as read were listed on the page when I looked; they can change, and I don't buy tickets." if with_times else "I couldn't read showtimes (theater sites usually draw them with scripts). These are playing near you: open the page to check times and buy tickets.")
                        else:
                            note = "Where to watch is only shown when a page said so; check your streaming services or rentals."
                        movie_out = MovieSearchOut(where=mr.where, movies=[MovieOut(title=m["title"], year=m["year"], genres=m["genres"], blurb=m["blurb"], where=m["where"], url=m["url"], watch_url=m["watch_url"], has_times=bool(m["slots"])) for m in movies], requested=mr.count, found=len(movies), unreadable=[UnreadableOut(**x) for x in found["unreadable"]], note=note, checked=checked)
                    except AIUnavailable as exc:
                        raise HTTPException(503, str(exc))
                    except Exception:
                        movies = []
                        movie_out = MovieSearchOut(where=mr.where, requested=mr.count, found=0, note="The movie search failed, so no movie nights were scheduled. Try again in a moment.", checked=checked)
                    _movie_cache[(user["id"], first)] = {"at": _time.time(), "sig": sig, "movies": movies, "out": movie_out}

    # The three searches don't depend on each other, so they run at the same time (each can take 20 to 40 seconds).
    searches = [f() for f, wanted in ((_find_classes, body.class_request), (_find_dinner, body.dinner_request), (_find_movies, body.movie_request)) if wanted]
    if searches:
        await asyncio.gather(*searches)

    notes = {"city": _clean(p.city, 80), "diet": _clean(p.diet, 500), "limits_note": _clean(p.limits_note, 500), "role": describe_role(p.role, p.role_details)}
    try:
        data = await run_planner(
            body.description,
            [g.model_dump() for g in body.goals],
            [a.model_dump() for a in body.answers],
            notes,
            p.wake_start,
            p.wake_end,
            free,
            first,
            days,
            tz,
            _now(tz),
            revision=_revision(body),
            classes=classes,
            class_req=class_req,
            priorities=body.priorities,
            venues=venues,
            dinner_req=dinner_req,
            ingredients=body.ingredients,
            movies=movies,
            movie_req=movie_req,
        )
    except AIUnavailable as exc:
        raise HTTPException(503, str(exc))
    except Exception:
        raise HTTPException(502, "Couldn't build your plan. Please try again in a moment.")  # never leak provider details
    return PlanResult(**data, used_calendar=body.free is not None, class_search=class_out, dinner_search=dinner_out, movie_search=movie_out)


class PrefetchBody(BaseModel):
    week_start: date
    class_request: ClassRequestIn | None = None
    dinner_request: DinnerRequestIn | None = None
    movie_request: MovieRequestIn | None = None


@router.post("/prefetch")
async def prefetch(body: PrefetchBody, user: dict = Depends(current_user)) -> dict:
    """Start the slow web searches for the requested classes, meal out and movie now, in the background, so the plan
    step is quick. Returns immediately. Nothing is shown to the user from this call and nothing is scheduled; the same
    AI limits apply as for a plan. The results are only used by /propose for the same request and week."""
    p = load_profile(user["id"])
    if not p.complete:
        raise HTTPException(409, "Save your profile first (waking hours and time zone).")
    first, _ = free_time.week_bounds(body.week_start, p.week_start)
    if first != body.week_start:
        raise HTTPException(400, "Pick the first day of a week.")
    days, started = 7, []
    if body.class_request and (city := _clean(body.class_request.city, 80) or _clean(p.city, 80)):
        cr = body.class_request
        studio, types = clean_line(cr.studio, 80), [t for t in (clean_line(x, 40) for x in cr.types) if t]
        _start_prefetch(user["id"], "class", first, _class_sig(cr, city), lambda: search_classes(city, cr.mode, studio, types, first, days))
        started.append("class")
    if body.dinner_request and (city := _clean(body.dinner_request.city, 80) or _clean(p.city, 80)):
        dr = body.dinner_request
        cuisines = [c for c in (clean_line(x, 40) for x in dr.cuisines) if c]
        _start_prefetch(user["id"], "dinner", first, _dinner_sig(dr, city), lambda: search_restaurants(city, clean_line(dr.named, 80), cuisines, dr.party, first, days, dr.style, dr.meal))
        started.append("dinner")
    if body.movie_request:
        mr = body.movie_request
        city = _clean(mr.city, 80) or _clean(p.city, 80)
        if mr.where == "home" or city:
            genres = [g for g in (clean_line(x, 30) for x in mr.genres) if g]
            _start_prefetch(user["id"], "movie", first, _movie_sig(mr, city), lambda: search_movies(city, mr.where, genres, first, days))
            started.append("movie")
    return {"started": started}


# ---------------- approve and export (design steps 5 and 6) ----------------


class ExportItem(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    kind: Literal["workout", "cooking", "social", "errand", "rest", "wellness", "other"]
    day: date
    start: str = Field(max_length=5)
    end: str = Field(max_length=5)
    why: str = Field(default="", max_length=300)
    notes: str = Field(default="", max_length=400)
    recipe: RecipeOut | None = None
    workout: WorkoutOut | None = None
    class_id: str | None = Field(default=None, max_length=12)
    venue_id: str | None = Field(default=None, max_length=12)
    movie_id: str | None = Field(default=None, max_length=12)
    evidence_ids: list[str] = Field(default_factory=list, max_length=6)
    goal_link: str = Field(default="", max_length=240)


class ExportBody(BaseModel):
    week_start: date
    free: list[SpanIn] | None = Field(default=None, max_length=600)
    priorities: list[str] = Field(default_factory=list, max_length=3)
    items: list[ExportItem] = Field(min_length=1, max_length=40)  # ONLY the items the user approved


def _clean_export_item(i: ExportItem) -> dict:
    d = {"class_id": re.sub(r"[^a-z0-9]", "", (i.class_id or "").lower())[:12] or None, "venue_id": re.sub(r"[^a-z0-9]", "", (i.venue_id or "").lower())[:12] or None, "movie_id": re.sub(r"[^a-z0-9]", "", (i.movie_id or "").lower())[:12] or None, "title": clean_line(i.title, 80), "kind": i.kind, "day": i.day, "start": i.start.strip(), "end": i.end.strip(), "why": clean_line(i.why, 200), "notes": clean_line(i.notes, 300), "recipe": None, "workout": None,
         "evidence_ids": [re.sub(r"[^a-z0-9_]", "", e.lower())[:40] for e in i.evidence_ids[:6]], "goal_link": clean_line(i.goal_link, 220)}
    if i.recipe and i.kind == "cooking":
        r = i.recipe
        d["recipe"] = {"servings": min(max(r.servings, 1), 12), "prep_minutes": min(max(r.prep_minutes, 0), 240), "cook_minutes": min(max(r.cook_minutes, 0), 240),
                       "ingredients": [x for x in (clean_line(v, 120) for v in r.ingredients[:40]) if x], "steps": [x for x in (clean_line(v, 300) for v in r.steps[:20]) if x]}
    if i.workout and i.kind == "workout":
        w = i.workout
        cl = lambda lst, n, each: [x for x in (clean_line(v, each) for v in lst[:n]) if x]
        d["workout"] = {"intensity": w.intensity, "equipment": cl(w.equipment, 10, 60), "warmup": cl(w.warmup, 8, 200), "main": cl(w.main, 12, 260), "cooldown": cl(w.cooldown, 8, 200), "adaptation_note": clean_line(w.adaptation_note, 240)}
    return d


@router.post("/export")
def export_plan(body: ExportBody, user: dict = Depends(current_user)) -> Response:
    """Build the .ics for the approved items. The items are re-validated here against the same rules as the proposal
    (free time, waking hours, buffers, diet notes), so nothing invalid can be exported. No model call."""
    p = load_profile(user["id"])
    if not p.complete:
        raise HTTPException(409, "Save your profile first (waking hours and time zone).")
    tz = ZoneInfo(p.timezone)
    first, _ = free_time.week_bounds(body.week_start, p.week_start)
    if first != body.week_start:
        raise HTTPException(400, "Pick the first day of a week.")
    h1, m1 = map(int, p.wake_start.split(":"))
    h2, m2 = map(int, p.wake_end.split(":"))
    day_list = [first + timedelta(days=i) for i in range(7)]
    free = _free_windows(body.free, day_list, h1, m1, h2, m2, tz)
    items = [_clean_export_item(i) for i in body.items]
    hit = _cached_classes(user["id"], first)
    class_map = {c["id"]: c for c in (hit["classes"] if hit else [])}
    if any(i["class_id"] for i in items) and not class_map:
        raise HTTPException(422, "Your class details have expired. Go back and propose the plan again to refresh them.")
    vhit = _cached_venues(user["id"], first)
    venue_map = {v["id"]: v for v in (vhit["venues"] if vhit else [])}
    if any(i["venue_id"] for i in items) and not venue_map:
        raise HTTPException(422, "Your restaurant details have expired. Go back and propose the plan again to refresh them.")
    mhit = _cached_movies(user["id"], first)
    movie_map = {m["id"]: m for m in (mhit["movies"] if mhit else [])}
    if any(i["movie_id"] for i in items) and not movie_map:
        raise HTTPException(422, "Your movie details have expired. Go back and propose the plan again to refresh them.")
    accepted, rejected = validate.validate_items(items, free, first, 7, time(h1, m1), time(h2, m2), tz, _clean(p.diet, 500), _now(tz), class_map, venue_map, movie_map)
    if rejected:
        problems = [{"title": r["item"]["title"], "reasons": r["reasons"]} for r in rejected]
        raise HTTPException(422, "Some approved items no longer fit your calendar or notes: " + "; ".join(f"{x['title']} ({' '.join(x['reasons'])})" for x in problems)[:600])
    # "Why this helps" is shown in the app only; the calendar file doesn't carry it.
    data = ics.build_ics(accepted, tz)
    return Response(
        content=data,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="week-plan-{first.isoformat()}.ics"'},
    )
