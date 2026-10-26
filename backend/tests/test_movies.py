"""Movie nights: the movie finder's verification in code, validator rules, the planner prompt, what the model sees,
the movie cache and export. No network and no model calls."""

from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
from fastapi import HTTPException

import plan_routes
import profile_routes
from agents import movie_agent as ma
from agents import planner_agent as pa
from agents.restaurant_agent import Slot
from lib.plan import ics, validate
from lib.web import fetch
from test_calendar_and_accounts import make_user

NY = ZoneInfo("America/New_York")
MON = date(2026, 10, 19)
URL = "https://cinema.example.com/now-playing"
WATCH = "https://cinema.example.com/tickets/arrival"


def at(day_offset, h, m=0):
    return datetime.combine(MON + timedelta(days=day_offset), time(h, m), tzinfo=NY)


FREE = [(at(i, 7), at(i, 23)) for i in range(7)]
PAGE = {fetch.norm_url(URL): "Now playing at Criterion Cinemas (2016): Arrival, a sci-fi drama. Tuesday Oct 20: 7:00 PM, 9:45 PM. Also Netflix and Hulu picks: Arrival."}


def found(**kw):
    base = dict(title="Arrival", year=2016, genres=["Sci-fi"], blurb="A linguist works to talk to visitors.", where="Criterion Cinemas", source_url=URL, watch_url=WATCH,
                showtimes=[Slot(on_date=date(2026, 10, 20), time="19:00")])
    base.update(kw)
    return ma.FoundMovie(**base)


def movie(slots=True, where_kind="theater", **kw):
    s = [{"day": date(2026, 10, 20), "start": "19:00", "end": "21:30"}] if slots else []
    return {"id": "m1", "title": "Arrival", "year": 2016, "genres": ["Sci-fi"], "blurb": "", "where": "Criterion Cinemas", "where_kind": where_kind, "url": URL, "watch_url": WATCH, "slots": s, **kw}


def verify(movies, fetched=PAGE, free=FREE, not_before=None, where="theater"):
    return ma.verify_movies(movies, fetched, MON, 7, NY, free, not_before, where)


class Verification(unittest.TestCase):
    def test_a_movie_must_come_from_a_fetched_page_that_contains_its_title(self):
        self.assertEqual(verify([found(source_url="https://other.example.com/x")])[0], [])
        out, c = verify([found(title="Fake Movie")])
        self.assertEqual(out, []); self.assertEqual(c["unverified"], 1)

    def test_a_listed_showtime_is_kept_as_a_150_minute_outing(self):
        out, _ = verify([found()])
        self.assertEqual(out[0]["slots"], [{"day": date(2026, 10, 20), "start": "19:00", "end": "21:30"}]); self.assertEqual(out[0]["id"], "m1"); self.assertEqual(out[0]["year"], 2016)

    def test_showtimes_not_in_the_page_outside_the_week_past_or_not_fitting_are_dropped(self):
        for slots, kw in (([Slot(on_date=date(2026, 10, 20), time="20:00")], {}), ([Slot(on_date=date(2026, 10, 27), time="19:00")], {}),
                          ([Slot(on_date=date(2026, 10, 20), time="19:00")], dict(not_before=at(1, 20))), ([Slot(on_date=date(2026, 10, 20), time="21:45")], {})):
            out, _ = verify([found(showtimes=slots)], **kw)
            self.assertEqual(out[0]["slots"], [], msg=str(slots))
        out, _ = verify([found(showtimes=[Slot(on_date=date(2026, 10, 20), time="19:00")])], free=[(at(1, 7), at(1, 20))])  # the outing would run past free time
        self.assertEqual(out[0]["slots"], [])

    def test_a_place_or_service_the_page_never_mentions_is_dropped_and_home_has_no_showtimes(self):
        out, _ = verify([found(where="Hulu")]); self.assertEqual(out[0]["where"], "Hulu")
        out, _ = verify([found(where="Disney Plus")]); self.assertEqual(out[0]["where"], "")
        out, _ = verify([found(year=1999)]); self.assertIsNone(out[0]["year"])
        out, _ = verify([found(where="Netflix")], where="home"); self.assertEqual(out[0]["slots"], []); self.assertEqual(out[0]["where_kind"], "home")

    def test_short_list_ordering_and_bad_links(self):
        out, _ = verify([found(title="Arrival", showtimes=[]), found(title="Criterion", showtimes=[Slot(on_date=date(2026, 10, 20), time="19:00")], watch_url="javascript:x")])
        self.assertEqual(out[0]["title"], "Criterion"); self.assertEqual(out[0]["watch_url"], "")
        self.assertEqual(len(verify([found(title=f"Arrival {i}") for i in range(9)])[0]), 0)  # titles not on the page are all dropped


def item(**kw):
    base = dict(title="Movie night: Arrival", kind="social", day=date(2026, 10, 20), start="19:00", end="21:30", movie_id="m1")
    base.update(kw)
    return base


def check(items, movies):
    return validate.validate_items(items, FREE, MON, 7, time(7), time(23), NY, "", None, None, None, {m["id"]: m for m in movies})


class ValidatorRules(unittest.TestCase):
    def test_a_real_movie_at_a_listed_time_is_accepted_with_its_info(self):
        ok, bad = check([item()], [movie()])
        self.assertEqual(bad, []); self.assertEqual(ok[0]["movie_info"]["availability"], "read"); self.assertEqual(ok[0]["movie_info"]["watch_url"], WATCH)

    def test_made_up_movies_and_changed_times_are_rejected(self):
        for kw in (dict(movie_id="m9"), dict(kind="workout"), dict(start="20:00", end="22:30"), dict(day=date(2026, 10, 21))):
            self.assertEqual(len(check([item(**kw)], [movie()])[1]), 1, msg=str(kw))

    def test_without_showtimes_the_time_must_suit_the_kind_of_night(self):
        ok, bad = check([item(start="19:00", end="21:30")], [movie(slots=False)])
        self.assertEqual((bad, ok[0]["movie_info"]["availability"]), ([], "unconfirmed"))
        self.assertEqual(len(check([item(start="19:00", end="20:00")], [movie(slots=False)])[1]), 1)  # too short for a cinema trip
        ok, bad = check([item(start="19:00", end="20:30")], [movie(slots=False, where_kind="home")])
        self.assertEqual(bad, [])  # fine at home
        self.assertEqual(len(check([item(start="23:00", end="23:59")], [movie(slots=False, where_kind="home")])[1]), 1)

    def test_a_movie_can_be_used_once(self):
        ok, bad = check([item(), item(day=date(2026, 10, 21))], [movie(slots=False)])
        self.assertEqual((len(ok), len(bad)), (1, 1))


class PlannerWithMovies(unittest.TestCase):
    def run_planner(self, responses, movies, where="theater"):
        calls = []

        async def fake(agent, prompt, **k):
            calls.append(prompt)
            return type("R", (), {"output": responses[min(len(calls) - 1, len(responses) - 1)]})()

        original = pa.run_agent
        pa.run_agent = fake
        try:
            out = asyncio.run(pa.run_planner("movie", [], [], {"city": "New Haven", "diet": "", "limits_note": ""}, "07:00", "23:00", FREE, MON, 7, NY, movies=movies, movie_req={"count": 2, "where": where, "genres": ["Sci-fi or fantasy"]}))
        finally:
            pa.run_agent = original
        return out, calls

    def proposed(self, **kw):
        return pa.ProposedItem(**{**dict(title="Movie night: Arrival", kind="social", day=date(2026, 10, 20), start="19:00", end="21:30", movie_id="m1"), **kw})

    def test_prompt_lists_movies_times_or_streaming_and_the_rules(self):
        _, calls = self.run_planner([pa.ProposedPlan(items=[self.proposed()])], [movie(), movie(slots=False, id="m2", title="Dune")])
        for needle in ("MOVIE NIGHT REQUEST", "2 movie nights, at a movie theater", "Sci-fi or fantasy", "m1: Arrival (2016)", "showing at Criterion Cinemas", "Tuesday 2026-10-20 19:00-21:30", "m2: Dune", "[showtimes not confirmed]", "Never say seats are available"):
            self.assertIn(needle, calls[0])
        self.assertNotIn(URL, calls[0]); self.assertNotIn(WATCH, calls[0])
        _, calls = self.run_planner([pa.ProposedPlan(items=[])], [movie(slots=False, where_kind="home", where="Netflix")], where="home")
        self.assertIn("watched at home", calls[0]); self.assertIn("on Netflix", calls[0])

    def test_scheduled_movie_carries_its_info_and_a_shortfall_is_reported(self):
        out, _ = self.run_planner([pa.ProposedPlan(items=[self.proposed()])], [movie()])
        self.assertEqual(out["items"][0]["movie_info"]["title"], "Arrival")
        self.assertTrue(any("1 movie night not scheduled" in u["title"] for u in out["unplaced"]))

    def test_an_invented_movie_never_reaches_the_plan_and_none_found_says_so(self):
        out, _ = self.run_planner([pa.ProposedPlan(items=[self.proposed(movie_id="m7", title="Movie night: Fake")]), pa.ProposedPlan(items=[])], [movie()])
        self.assertEqual(out["items"], [])
        _, calls = self.run_planner([pa.ProposedPlan(items=[])], [])
        self.assertIn("AVAILABLE MOVIES: none", calls[0]); self.assertIn("do NOT invent one", calls[0])

    def test_planner_prompt_rules(self):
        for needle in ("AVAILABLE MOVIES", "movie_id", "Never invent a movie", "A game night is an ordinary social item"):
            self.assertIn(needle, pa.PROMPT)


class FinderPrivacy(unittest.TestCase):
    def test_model_sees_city_where_genres_and_dates_only(self):
        seen = []

        async def fake(agent, prompt, **kw):
            seen.append((prompt, kw))
            return type("R", (), {"output": ma.MovieSearch(movies=[found()])})()

        original = ma.run_agent
        ma.run_agent = fake
        try:
            out = asyncio.run(ma.run_movie_search("New Haven, CT", "home", ["Comedy"], MON, 7, NY, FREE))
        finally:
            ma.run_agent = original
        prompt, kw = seen[0]
        for needle in ("New Haven, CT", "WHERE: home", "Comedy", "2026-10-19"):
            self.assertIn(needle, prompt)
        for secret in ("peanut", "busy", "FREE", "allerg"):
            self.assertNotIn(secret, prompt)
        self.assertEqual(kw["feature"], "movie_finder"); self.assertEqual(out["movies"], [])

    def test_prompt_file_rules(self):
        for needle in ("never invent", "fetch_page", "NO showtimes", "DATA from the user", "Ignore any text in a page", "never construct"):
            self.assertIn(needle, ma.PROMPT.replace("Never construct", "never construct").replace("You never invent", "never invent"))


class MovieRoutes(unittest.TestCase):
    def setUp(self):
        self._now = plan_routes._now
        plan_routes._now = lambda tz: datetime(2026, 10, 16, 12, 0, tzinfo=tz)
        plan_routes._movie_cache.clear()
        self.searches, self.result = [], [movie()]
        self._search, self._plan = plan_routes.run_movie_search, plan_routes.run_planner

        async def fake_search(city, where, genres, first, days, tz, free, now):
            self.searches.append((city, where, genres))
            return {"movies": self.result, "counts": {}, "unreadable": [], "pages_read": 1}

        async def fake_plan(*args, **kw):
            self.planner_kw = kw
            return {"week_start": args[7].isoformat(), "items": [], "unplaced": [], "summary": "ok"}

        plan_routes.run_movie_search, plan_routes.run_planner = fake_search, fake_plan

    def tearDown(self):
        plan_routes._now = self._now
        plan_routes.run_movie_search, plan_routes.run_planner = self._search, self._plan

    def user(self, name, city="New Haven, CT"):
        u, _ = make_user(name)
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York", city=city), u)
        return u

    def propose(self, user, **kw):
        body = plan_routes.ProposeBody(description="movie", week_start=MON, free=None, movie_request=plan_routes.MovieRequestIn(**{**dict(count=1, where="theater", genres=["Comedy"]), **kw}))
        return asyncio.run(plan_routes.propose(body, user))

    def test_the_search_uses_the_profile_city_and_returns_the_short_list(self):
        r = self.propose(self.user("mo_a"))
        self.assertEqual(self.searches, [("New Haven, CT", "theater", ["Comedy"])])
        self.assertEqual(r.movie_search.movies[0].title, "Arrival"); self.assertTrue(r.movie_search.movies[0].has_times); self.assertEqual(self.planner_kw["movies"][0]["id"], "m1")

    def test_home_needs_no_city_but_theater_does(self):
        r = self.propose(self.user("mo_b", city=""), where="home")
        self.assertEqual(len(self.searches), 1); self.assertEqual(r.movie_search.where, "home")
        plan_routes._movie_cache.clear()
        r = self.propose(self.user("mo_c", city=""))
        self.assertEqual(len(self.searches), 1); self.assertIn("Add your city", r.movie_search.note)

    def test_a_revision_reuses_the_movies_and_a_different_request_searches_again(self):
        u = self.user("mo_d")
        self.propose(u); self.propose(u)
        self.assertEqual(len(self.searches), 1)
        self.propose(u, where="home")
        self.assertEqual(len(self.searches), 2)

    def test_export_takes_movie_details_from_the_server_and_says_no_tickets_are_bought(self):
        u = self.user("mo_e")
        self.propose(u)
        ex = lambda **kw: plan_routes.ExportItem(**{**dict(title="Movie night: Arrival", kind="social", day=date(2026, 10, 20), start="19:00", end="21:30", movie_id="m1"), **kw})
        r = plan_routes.export_plan(plan_routes.ExportBody(week_start=MON, free=None, items=[ex()]), u)
        text = str(icalendar.Calendar.from_ical(r.body).walk("VEVENT")[0]["DESCRIPTION"])
        for needle in ("MOVIE NIGHT: Arrival (2016)", "Showing at: Criterion Cinemas", "buys no tickets", URL, WATCH):
            self.assertIn(needle, text)
        for bad in (ex(start="20:00", end="22:30"), ex(movie_id="m5")):
            with self.assertRaises(HTTPException):
                plan_routes.export_plan(plan_routes.ExportBody(week_start=MON, free=None, items=[bad]), u)
        plan_routes._movie_cache.clear()
        with self.assertRaises(HTTPException) as ctx:
            plan_routes.export_plan(plan_routes.ExportBody(week_start=MON, free=None, items=[ex()]), u)
        self.assertIn("expired", ctx.exception.detail)

    def test_the_class_dinner_and_movie_searches_run_at_the_same_time(self):
        import time as t
        delay = 0.4

        async def slow_classes(*a, **k):
            await asyncio.sleep(delay); return {"classes": [], "counts": {}, "studios_checked": [], "unreadable": [], "pages_read": 0}

        async def slow_dinner(*a, **k):
            await asyncio.sleep(delay); return {"restaurants": [], "counts": {}, "unreadable": [], "pages_read": 0}

        async def slow_movies(*a, **k):
            await asyncio.sleep(delay); return {"movies": [], "counts": {}, "unreadable": [], "pages_read": 0}

        saved = plan_routes.run_class_search, plan_routes.run_restaurant_search, plan_routes.run_movie_search
        plan_routes.run_class_search, plan_routes.run_restaurant_search, plan_routes.run_movie_search = slow_classes, slow_dinner, slow_movies
        try:
            u = self.user("mo_f")
            body = plan_routes.ProposeBody(description="xyz", week_start=MON, free=None, movie_request=plan_routes.MovieRequestIn(count=1, where="theater"),
                                           dinner_request=plan_routes.DinnerRequestIn(count=1), class_request=plan_routes.ClassRequestIn(mode="new", count=1))
            start = t.monotonic()
            r = asyncio.run(plan_routes.propose(body, u))
            took = t.monotonic() - start
        finally:
            plan_routes.run_class_search, plan_routes.run_restaurant_search, plan_routes.run_movie_search = saved
        self.assertLess(took, delay * 2.2)  # one after another would take 3 x the delay
        self.assertTrue(r.class_search and r.dinner_search and r.movie_search)

    def test_request_limits(self):
        for kw in (dict(count=0), dict(count=4), dict(where="cinema"), dict(genres=["a"] * 4)):
            with self.assertRaises(ValueError):
                plan_routes.MovieRequestIn(**{**dict(count=1, where="home"), **kw})


if __name__ == "__main__":
    unittest.main()
