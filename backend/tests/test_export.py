"""Steps 5 and 6: the .ics export. Only approved, re-validated items are exported, and the file can't be tampered with by text."""

from __future__ import annotations

import unittest
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import icalendar
from fastapi import HTTPException

import plan_routes
import profile_routes
from lib.plan import ics
from test_calendar_and_accounts import make_user

NY = ZoneInfo("America/New_York")
MON = date(2026, 10, 19)
DST_WEEK = date(2026, 10, 26)  # DST ends Sunday Nov 1


def item(title="Strength", kind="workout", day=MON, start="07:30", end="08:15", **kw):
    base = dict(title=title, kind=kind, day=day, start=start, end=end, why="morning is free", notes="")
    base.update(kw)
    return base


def parse(data: bytes):
    cal = icalendar.Calendar.from_ical(data)
    return cal, [c for c in cal.walk() if c.name == "VEVENT"]


class IcsFile(unittest.TestCase):
    def test_file_is_a_valid_calendar_with_one_event_per_item(self):
        cal, events = parse(ics.build_ics([item(), item("Dinner", "cooking", start="18:00", end="19:00")], NY))
        self.assertEqual(len(events), 2)
        self.assertEqual(str(cal["VERSION"]), "2.0"); self.assertIn("Week Planner", str(cal["PRODID"]))
        e = events[0]
        self.assertEqual(str(e["SUMMARY"]), "Strength"); self.assertEqual(e.start, datetime(2026, 10, 19, 7, 30, tzinfo=NY)); self.assertEqual(e.end, datetime(2026, 10, 19, 8, 15, tzinfo=NY))

    def test_events_have_unique_ids_and_timezone_definitions(self):
        data = ics.build_ics([item(), item("B", start="09:30", end="10:00")], NY)
        _, events = parse(data)
        self.assertEqual(len({str(e["UID"]) for e in events}), 2)
        self.assertIn(b"BEGIN:VTIMEZONE", data); self.assertIn(b"America/New_York", data)
        self.assertNotIn(b"METHOD", data)  # a plain file to import, not an invitation

    def test_times_keep_the_wall_clock_across_a_dst_change(self):
        sat = item(day=DST_WEEK + timedelta(days=5), start="10:00", end="11:00")  # Sat Oct 31: still EDT
        sun = item(day=DST_WEEK + timedelta(days=6), start="10:00", end="11:00")  # Sun Nov 1: EST
        _, events = parse(ics.build_ics([sat, sun], NY))
        offsets = sorted(e.start.utcoffset() for e in events)
        self.assertEqual([e.start.hour for e in events], [10, 10]); self.assertEqual(offsets, [timedelta(hours=-5), timedelta(hours=-4)])

    def test_recipe_and_workout_details_go_in_the_description(self):
        dinner = item("Dinner", "cooking", start="18:00", end="19:00", recipe={"servings": 2, "prep_minutes": 10, "cook_minutes": 20, "ingredients": ["2 cups rice", "1 tbsp olive oil"], "steps": ["Boil rice", "Serve"]})
        lift = item(workout={"intensity": "easy", "equipment": ["dumbbells"], "warmup": ["March in place"], "main": ["Glute bridges"], "cooldown": ["Stretch"], "adaptation_note": "No deep squats because of your knee"})
        _, events = parse(ics.build_ics([dinner, lift], NY))
        texts = {str(e["SUMMARY"]): str(e["DESCRIPTION"]) for e in events}
        self.assertIn("2 cups rice", texts["Dinner"]); self.assertIn("1. Boil rice", texts["Dinner"])
        self.assertIn("Glute bridges", texts["Strength"]); self.assertIn("No deep squats", texts["Strength"])
        for d in texts.values():
            self.assertIn("not medical advice", d)

    def test_text_cannot_inject_calendar_lines_or_links(self):
        evil = item(title="Run\r\nEND:VEVENT\r\nBEGIN:VEVENT\r\nSUMMARY:Injected", why="see https://evil.example/x", notes="a, b; c\nnew line <b>x</b>")
        data = ics.build_ics([evil], NY)
        _, events = parse(data)
        self.assertEqual(len(events), 1)  # no second event was smuggled in
        self.assertNotIn(b"evil.example", data); self.assertNotIn(b"<b>", data)
        self.assertNotIn("Injected", [str(e["SUMMARY"]) for e in events])

    def test_the_word_safe_is_never_written_into_the_file(self):
        data = ics.build_ics([item(title="A safe workout", why="totally safe")], NY)
        self.assertNotRegex(data.decode().lower(), r"\bsafe\b")


class ExportRoute(unittest.TestCase):
    def setUp(self):
        self._now = plan_routes._now
        plan_routes._now = lambda tz: datetime(2026, 10, 16, 12, 0, tzinfo=tz)  # pin the clock: Fri Oct 16 2026, noon
        self.user, _ = make_user(f"zed{id(self) % 9999}")
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York", wake_start="07:00", wake_end="22:00", diet="peanut allergy"), self.user)

    def tearDown(self):
        plan_routes._now = self._now

    def export(self, items, free=None, week=MON, user=None):
        body = plan_routes.ExportBody(week_start=week, free=free, items=items)
        return plan_routes.export_plan(body, user or self.user)

    def ex(self, title="Strength", kind="workout", **kw):
        base = dict(title=title, kind=kind, day=MON, start="07:30", end="08:15")
        base.update(kw)
        return plan_routes.ExportItem(**base)

    def test_approved_items_become_a_downloadable_ics(self):
        r = self.export([self.ex()])
        self.assertEqual(r.media_type, "text/calendar; charset=utf-8")
        self.assertIn("attachment", r.headers["content-disposition"]); self.assertIn("week-plan-2026-10-19.ics", r.headers["content-disposition"])
        _, events = parse(r.body)
        self.assertEqual(len(events), 1)

    def test_only_what_is_sent_is_exported(self):
        r = self.export([self.ex("A"), self.ex("B", start="09:00", end="09:45")])
        self.assertEqual(sorted(str(e["SUMMARY"]) for e in parse(r.body)[1]), ["A", "B"])
        self.assertEqual(len(parse(self.export([self.ex("A")]).body)[1]), 1)  # the unapproved B isn't there

    def test_items_are_revalidated_against_the_calendar_on_export(self):
        busy_morning = [plan_routes.SpanIn(start=datetime(2026, 10, 19, 12, tzinfo=NY), end=datetime(2026, 10, 19, 20, tzinfo=NY))]
        with self.assertRaises(HTTPException) as ctx:
            self.export([self.ex()], free=busy_morning)  # 07:30 is not inside the free windows given
        self.assertEqual(ctx.exception.status_code, 422); self.assertIn("Strength", ctx.exception.detail)

    def test_overlaps_waking_hours_and_diet_conflicts_are_refused(self):
        for items in ([self.ex("A"), self.ex("B", start="08:00", end="08:30")],  # no gap
                      [self.ex(start="05:00", end="05:45")],  # before waking hours
                      [self.ex("Dinner", "cooking", start="18:00", end="19:00", recipe=plan_routes.RecipeOut(servings=2, prep_minutes=5, cook_minutes=20, ingredients=["peanut sauce"], steps=["cook"]))]):
            with self.assertRaises(HTTPException) as ctx:
                self.export(items)
            self.assertEqual(ctx.exception.status_code, 422)

    def test_items_in_the_past_cannot_be_exported(self):
        with self.assertRaises(HTTPException) as ctx:
            self.export([self.ex(day=date(2026, 10, 13), start="18:00", end="19:00")], week=date(2026, 10, 12))  # Tuesday of the week in progress
        self.assertEqual(ctx.exception.status_code, 422); self.assertIn("already passed", ctx.exception.detail)
        self.assertEqual(len(parse(self.export([self.ex(day=date(2026, 10, 17), start="10:00", end="11:00")], week=date(2026, 10, 12)).body)[1]), 1)  # tomorrow is fine

    def test_week_must_start_on_the_users_week_start_and_profile_is_needed(self):
        with self.assertRaises(HTTPException) as ctx:
            self.export([self.ex(day=MON + timedelta(days=2))], week=MON + timedelta(days=2))
        self.assertEqual(ctx.exception.status_code, 400)
        fresh, _ = make_user(f"fresh{id(self) % 9999}")
        with self.assertRaises(HTTPException) as ctx:
            self.export([self.ex()], user=fresh)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_request_limits(self):
        for kw in (dict(items=[]), dict(items=[self.ex()] * 41)):
            with self.assertRaises(ValueError):
                plan_routes.ExportBody(week_start=MON, **kw)
        with self.assertRaises(ValueError):
            plan_routes.ExportItem(title="", kind="workout", day=MON, start="07:00", end="08:00")


if __name__ == "__main__":
    unittest.main()
