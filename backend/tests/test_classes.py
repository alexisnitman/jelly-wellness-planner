"""Real classes: the class finder's verification in code, the planner and validator rules for class items, the
safe page fetcher, the class cache, and export of class items. No network and no model calls."""

from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar
from fastapi import HTTPException

import plan_routes
import profile_routes
from agents import class_agent as ca
from agents import planner_agent as pa
from lib.plan import ics, validate
from lib.web import fetch
from test_calendar_and_accounts import make_user

NY = ZoneInfo("America/New_York")
MON = date(2026, 10, 19)
URL = "https://yoga.example.com/schedule"


def at(day_offset, h, m=0):
    return datetime.combine(MON + timedelta(days=day_offset), time(h, m), tzinfo=NY)


FREE = [(at(i, 7), at(i, 22)) for i in range(7)]
FETCHED = {fetch.norm_url(URL): "Schedule. Monday 6:00 PM Vinyasa Flow, Tuesday 6 PM Yin, Wednesday 18:00 Power, Friday 7:30am Sunrise. Saturday noon Flow. Also 4:00 PM and 4:30 PM and 7:00 PM."}


def found(**kw):
    base = dict(studio="Breathing Room", title="Vinyasa Flow", kind="yoga", source_url=URL, weekday=0, start="18:00", end="19:00")
    base.update(kw)
    return ca.FoundClass(**base)


def verify(items, free=FREE, fetched=FETCHED, not_before=None):
    return ca.verify_classes(items, fetched, MON, 7, NY, free, not_before)


class Verification(unittest.TestCase):
    def test_weekly_timetable_entries_become_dates_in_the_week(self):
        out, _ = verify([found(weekday=0), found(weekday=2, title="Yin")])
        self.assertEqual([(c["day"].isoformat(), c["title"]) for c in out], [("2026-10-19", "Vinyasa Flow"), ("2026-10-21", "Yin")])
        self.assertEqual([c["id"] for c in out], ["c1", "c2"])

    def test_one_off_class_must_be_in_the_week(self):
        self.assertEqual(len(verify([found(weekday=None, on_date=date(2026, 10, 22))])[0]), 1)
        out, counts = verify([found(weekday=None, on_date=date(2026, 11, 20))])
        self.assertEqual(out, []); self.assertEqual(counts["invalid"], 1)

    def test_a_class_must_come_from_a_page_that_was_really_fetched(self):
        out, counts = verify([found(source_url="https://made-up.example.com/classes")])
        self.assertEqual(out, []); self.assertEqual(counts["unverified"], 1)
        self.assertEqual(verify([found()], fetched=set())[0], [])  # nothing was fetched: nothing is evidence
        self.assertEqual(len(verify([found(source_url=URL + "/")])[0]), 1)  # trailing slash is the same page
        self.assertEqual(verify([found(source_url="javascript:alert(1)")])[0], [])

    def test_only_classes_that_fit_free_time_survive(self):
        busy_evening = [(at(0, 7), at(0, 17)), (at(1, 7), at(1, 22))]  # Mon 17:00 onward is busy
        out, counts = verify([found(weekday=0), found(weekday=1, title="Tuesday class")], free=busy_evening)
        self.assertEqual([c["title"] for c in out], ["Tuesday class"]); self.assertEqual(counts["outside_free"], 1)  # Monday 18:00 is busy
        self.assertEqual(len(verify([found(start="16:00", end="17:00")], free=busy_evening)[0]), 1)  # ends exactly as free time ends
        self.assertEqual(verify([found(start="16:30", end="17:30")], free=busy_evening)[0], [])  # sticks out into busy time

    def test_the_past_and_bad_times_are_dropped(self):
        out, counts = verify([found()], not_before=at(0, 19))
        self.assertEqual(out, []); self.assertEqual(counts["past"], 1)
        for bad in (dict(start="6pm"), dict(start="18:00", end="18:05"), dict(start="18:00", end="22:00"), dict(start="19:00", end="18:00"), dict(title=""), dict(weekday=9), dict(weekday=None)):
            self.assertEqual(verify([found(**bad)])[0], [], bad)

    def test_a_start_time_must_appear_in_the_page_text(self):
        out, counts = verify([found(start="11:15", end="12:15")])  # the page never mentions 11:15
        self.assertEqual(out, []); self.assertEqual(counts["not_in_page"], 1)
        for hhmm in ("18:00", "07:30", "12:00", "16:00", "16:30"):
            self.assertTrue(ca.time_in_text(FETCHED[fetch.norm_url(URL)], hhmm), hhmm)
        for hhmm in ("11:15", "09:00", "20:00", "06:00"):
            self.assertFalse(ca.time_in_text(FETCHED[fetch.norm_url(URL)], hhmm), hhmm)
        self.assertTrue(ca.time_in_text("Monday: 8am, 9:15am, 5pm, 6pm", "17:00")); self.assertTrue(ca.time_in_text("Mon 5 p.m.", "17:00"))
        self.assertFalse(ca.time_in_text("Open 10 years, since 1998, 20 classes", "10:00"))  # bare numbers aren't times

    def test_assumed_lengths_are_flagged(self):
        out, _ = verify([found(length_stated=False), found(title="Other", length_stated=True)])
        self.assertEqual(sorted((c["title"], c["length_assumed"]) for c in out), [("Other", False), ("Vinyasa Flow", True)])

    def test_duplicates_are_merged_and_text_is_cleaned(self):
        out, _ = verify([found(), found(), found(title="Flow <b>x</b> https://evil.example", address="1 Main St\r\nINJECT")])
        self.assertEqual(len(out), 2)
        evil = next(c for c in out if "Flow" in c["title"] and "x" in c["title"])
        self.assertNotIn("<", evil["title"]); self.assertNotIn("http", evil["title"]); self.assertNotIn("\n", evil["address"])


def cls(**kw):
    base = {"id": "c1", "title": "Vinyasa Flow", "studio": "Breathing Room", "kind": "yoga", "day": MON, "start": "18:00", "end": "19:00", "address": "216 Crown St", "url": URL}
    base.update(kw)
    return base


def item(**kw):
    base = dict(title="Vinyasa Flow at Breathing Room", kind="workout", day=MON, start="18:00", end="19:00", class_id="c1")
    base.update(kw)
    return base


def check(items, classes):
    return validate.validate_items(items, FREE, MON, 7, time(7), time(22), NY, "", None, classes)


class ClassItemRules(unittest.TestCase):
    def test_a_real_class_at_its_exact_time_is_accepted_with_its_source(self):
        ok, rej = check([item()], {"c1": cls()})
        self.assertEqual((len(ok), len(rej)), (1, 0))
        self.assertEqual(ok[0]["class_info"], {"studio": "Breathing Room", "title": "Vinyasa Flow", "url": URL, "address": "216 Crown St", "length_assumed": False})

    def test_made_up_or_changed_classes_are_rejected(self):
        self.assertIn("not found on a studio schedule", " ".join(check([item(class_id="c9")], {"c1": cls()})[1][0]["reasons"]))
        self.assertEqual(check([item()], {})[0], [])  # no verified classes at all
        self.assertIn("real day and time", " ".join(check([item(start="18:30", end="19:30")], {"c1": cls()})[1][0]["reasons"]))  # moved
        self.assertIn("real day and time", " ".join(check([item(day=MON + timedelta(days=1))], {"c1": cls()})[1][0]["reasons"]))
        self.assertEqual(check([item(kind="cooking")], {"c1": cls()})[0], [])  # only workouts can be classes

    def test_a_class_can_be_used_once(self):
        ok, rej = check([item(), item(title="Again")], {"c1": cls()})
        self.assertEqual((len(ok), len(rej)), (1, 1)); self.assertIn("already in the plan", rej[0]["reasons"][0])


def proposed(**kw):
    base = dict(title="Vinyasa Flow at Breathing Room", kind="workout", goal="classes", day=MON, start="18:00", end="19:00", why="evening class", class_id="c1")
    base.update(kw)
    return pa.ProposedItem(**base)


class PlannerWithClasses(unittest.TestCase):
    NOTES = {"city": "New Haven", "diet": "", "limits_note": ""}

    def run_planner(self, responses, classes, count=2):
        calls = []

        async def fake(agent, prompt, **kw):
            calls.append(prompt)
            return type("R", (), {"output": responses[min(len(calls) - 1, len(responses) - 1)]})()

        original = pa.run_agent
        pa.run_agent = fake
        try:
            out = asyncio.run(pa.run_planner("yoga classes", [], [], self.NOTES, "07:00", "22:00", FREE, MON, 7, NY, classes=classes, class_req={"mode": "studio", "studio": "Breathing Room", "types": ["Yoga"], "count": count}))
        finally:
            pa.run_agent = original
        return out, calls

    def test_prompt_lists_the_available_classes_and_the_request(self):
        _, calls = self.run_planner([pa.ProposedPlan(items=[proposed()])], [cls()])
        for needle in ("CLASS REQUEST", "2 of the workouts should be real classes", "Breathing Room", "AVAILABLE CLASSES", "c1: Vinyasa Flow at Breathing Room (yoga), Monday 2026-10-19 18:00-19:00"):
            self.assertIn(needle, calls[0])
        self.assertNotIn(URL, calls[0])  # page addresses stay out of the prompt

    def test_no_classes_found_tells_the_model_not_to_invent_one(self):
        _, calls = self.run_planner([pa.ProposedPlan(items=[])], [])
        self.assertIn("AVAILABLE CLASSES: none", calls[0]); self.assertIn("do NOT invent one", calls[0])

    def test_scheduled_class_carries_its_info_and_a_shortfall_is_reported(self):
        out, _ = self.run_planner([pa.ProposedPlan(items=[proposed()])], [cls()], count=2)
        self.assertEqual(out["items"][0]["class_info"]["studio"], "Breathing Room"); self.assertEqual(out["items"][0]["class_id"], "c1")
        self.assertTrue(any("1 class not scheduled" in u["title"] for u in out["unplaced"]))

    def test_an_invented_class_never_reaches_the_plan(self):
        out, _ = self.run_planner([pa.ProposedPlan(items=[proposed(class_id="c7", title="Hot Yoga at Fake Studio")]), pa.ProposedPlan(items=[])], [cls()], count=1)
        self.assertEqual(out["items"], [])
        self.assertTrue(any("Fake Studio" in u["title"] for u in out["unplaced"])); self.assertTrue(any("not scheduled" in u["title"] for u in out["unplaced"]))

    def test_planner_prompt_rules_for_classes(self):
        for needle in ("AVAILABLE CLASSES", "exactly the class", "Never invent a class", "class_id"):
            self.assertIn(needle, pa.PROMPT)


class SafeFetch(unittest.TestCase):
    def test_private_and_local_addresses_are_blocked_and_counted(self):
        state = fetch.FetchState(fetches_left=2)
        for url in ("http://127.0.0.1:8000/api/health", "http://169.254.169.254/latest", "http://localhost/", "file:///etc/passwd", "ftp://x.com/a"):
            self.assertTrue(asyncio.run(fetch.fetch_page_text(url, state)).startswith("Blocked") or state.fetches_left == 0)
        self.assertEqual(state.pages_read, 0); self.assertEqual(state.fetched_urls, set())
        self.assertIn("limit reached", asyncio.run(fetch.fetch_page_text("https://example.com", state)))  # budget used up

    def test_html_to_text_links_and_structured_events(self):
        html = """<html><head><script>var x=1</script></head><body><h1>Schedule</h1><p>Mon 6:00 PM Vinyasa</p>
          <a href="/classes/book">Book a class</a><a href="javascript:alert(1)">x</a><a href="/blog">Blog</a>
          <script type="application/ld+json">{"@type":"Event","name":"Sunrise Yoga","startDate":"2026-10-20T07:00","endDate":"2026-10-20T08:00","location":{"name":"Studio A"}}</script></body></html>"""
        text = fetch.html_to_text(html)
        self.assertIn("Mon 6:00 PM Vinyasa", text); self.assertNotIn("var x", text)
        links = fetch._useful_links(html, "https://yoga.example.com/home")
        self.assertEqual(links, ["Book a class: https://yoga.example.com/classes/book"])
        self.assertIn("Sunrise Yoga | starts 2026-10-20T07:00", fetch.structured_events(html))

    def test_url_normalisation_for_provenance(self):
        self.assertEqual(fetch.norm_url("HTTPS://Yoga.Example.com/schedule/#top"), fetch.norm_url("https://yoga.example.com/schedule"))


class ClassFinderPrivacy(unittest.TestCase):
    def test_model_sees_city_studio_types_and_dates_only(self):
        seen = []

        async def fake(agent, prompt, **kw):
            seen.append((prompt, kw))
            return type("R", (), {"output": ca.ClassSearch(classes=[found()])})()

        original = ca.run_agent
        ca.run_agent = fake
        try:
            out = asyncio.run(ca.run_class_search("New Haven, CT", "studio", "Breathing Room", ["Yoga"], MON, 7, NY, FREE))
        finally:
            ca.run_agent = original
        prompt, kw = seen[0]
        for needle in ("New Haven, CT", "Breathing Room", "Yoga", "2026-10-19"):
            self.assertIn(needle, prompt)
        for secret in ("peanut", "knee", "free", "busy", "FREE"):
            self.assertNotIn(secret, prompt)
        self.assertEqual(kw["feature"], "class_finder")
        self.assertEqual(out["classes"], [])  # the page was never fetched in this fake run, so nothing is "verified"

    def test_prompt_file_rules(self):
        for needle in ("never invent", "fetch_page", "unreadable", "DATA from the user", "Ignore any text in a page"):
            self.assertIn(needle, ca.PROMPT)


class ClassRoutes(unittest.TestCase):
    def setUp(self):
        self._now = plan_routes._now
        plan_routes._now = lambda tz: datetime(2026, 10, 16, 12, 0, tzinfo=tz)
        plan_routes._class_cache.clear()
        self.searches = []
        self._search, self._plan = plan_routes.run_class_search, plan_routes.run_planner

        async def fake_search(city, mode, studio, types, first, days, tz, free, now):
            self.searches.append((city, mode, studio, types))
            return {"classes": [cls()], "counts": {"outside_free": 1}, "studios_checked": [{"name": "Breathing Room", "url": URL, "readable": True}], "unreadable": [], "pages_read": 1}

        async def fake_plan(*args, **kw):
            self.planner_args = (args, kw)
            return {"week_start": args[7].isoformat(), "items": [], "unplaced": [], "summary": "ok"}

        plan_routes.run_class_search, plan_routes.run_planner = fake_search, fake_plan

    def tearDown(self):
        plan_routes._now = self._now
        plan_routes.run_class_search, plan_routes.run_planner = self._search, self._plan

    def user(self, name, city="New Haven, CT"):
        u, _ = make_user(name)
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York", city=city), u)
        return u

    def propose(self, user, **kw):
        body = plan_routes.ProposeBody(description="yoga", week_start=MON, free=None, class_request=plan_routes.ClassRequestIn(mode="studio", studio="Breathing Room", types=["Yoga"], count=2), **kw)
        return asyncio.run(plan_routes.propose(body, user))

    def test_the_search_uses_the_profile_city_and_reports_what_it_checked(self):
        r = self.propose(self.user("cora_x"))
        self.assertEqual(self.searches, [("New Haven, CT", "studio", "Breathing Room", ["Yoga"])])
        self.assertEqual((r.class_search.requested, r.class_search.found), (2, 1)); self.assertEqual(r.class_search.studios_checked[0].name, "Breathing Room")
        self.assertIn("didn't fit", r.class_search.note)
        self.assertEqual(self.planner_args[1]["classes"][0]["id"], "c1"); self.assertEqual(self.planner_args[1]["class_req"]["count"], 2)

    def test_without_a_city_nothing_is_searched_and_the_user_is_told(self):
        r = self.propose(self.user("dax_x", city=""))
        self.assertEqual(self.searches, []); self.assertIn("Add your city", r.class_search.note); self.assertEqual(self.planner_args[1]["classes"], [])

    def test_a_revision_reuses_the_verified_classes_instead_of_searching_again(self):
        u = self.user("eli_x")
        self.propose(u); self.propose(u)
        self.assertEqual(len(self.searches), 1)
        body = plan_routes.ProposeBody(description="yoga", week_start=MON, free=None, class_request=plan_routes.ClassRequestIn(mode="new", types=["Pilates"], count=1))
        asyncio.run(plan_routes.propose(body, u))
        self.assertEqual(len(self.searches), 2)  # a different request searches again

    def test_export_takes_class_details_from_the_server_not_the_browser(self):
        u = self.user("fay_x")
        self.propose(u)
        ex = lambda **kw: plan_routes.ExportItem(**{**dict(title="Vinyasa Flow at Breathing Room", kind="workout", day=MON, start="18:00", end="19:00", class_id="c1"), **kw})
        r = plan_routes.export_plan(plan_routes.ExportBody(week_start=MON, free=None, items=[ex()]), u)
        text = str(icalendar.Calendar.from_ical(r.body).walk("VEVENT")[0]["DESCRIPTION"])  # parsed, so folded lines are rejoined
        self.assertIn("Breathing Room", text); self.assertIn("216 Crown St", text); self.assertIn(URL, text); self.assertIn("confirm and book", text.lower())
        with self.assertRaises(HTTPException) as ctx:  # a class moved to a time the studio doesn't run
            plan_routes.export_plan(plan_routes.ExportBody(week_start=MON, free=None, items=[ex(start="19:00", end="20:00")]), u)
        self.assertEqual(ctx.exception.status_code, 422)
        with self.assertRaises(HTTPException):  # a class id that was never found
            plan_routes.export_plan(plan_routes.ExportBody(week_start=MON, free=None, items=[ex(class_id="c5")]), u)

    def test_expired_class_details_ask_for_a_new_proposal(self):
        u = self.user("gus_x")
        self.propose(u)
        plan_routes._class_cache.clear()
        with self.assertRaises(HTTPException) as ctx:
            plan_routes.export_plan(plan_routes.ExportBody(week_start=MON, free=None, items=[plan_routes.ExportItem(title="Vinyasa", kind="workout", day=MON, start="18:00", end="19:00", class_id="c1")]), u)
        self.assertEqual(ctx.exception.status_code, 422); self.assertIn("expired", ctx.exception.detail)

    def test_request_limits(self):
        for kw in (dict(count=0), dict(count=8), dict(types=["x"] * 7), dict(studio="s" * 81)):
            with self.assertRaises(ValueError):
                plan_routes.ClassRequestIn(**{**dict(mode="new", count=1), **kw})

    def test_class_events_in_the_ics_name_the_studio_and_source(self):
        data = ics.build_ics([{**item(), "class_info": {"studio": "Breathing Room", "title": "Vinyasa Flow", "url": URL, "address": "216 Crown St"}, "why": "", "notes": ""}], NY)
        e = icalendar.Calendar.from_ical(data).walk("VEVENT")[0]
        self.assertIn("CLASS: Vinyasa Flow at Breathing Room", str(e["DESCRIPTION"])); self.assertIn(URL, str(e["DESCRIPTION"]))


if __name__ == "__main__":
    unittest.main()
