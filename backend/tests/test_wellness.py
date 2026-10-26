"""The purpose of the app: a sustainable routine and wellness for busy students and professionals. Rules that protect
sleep and prevent overloading, the new wellness item kind, and the principles in the prompts."""

from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar

import interview_routes
import plan_routes
from agents import interview_agent as ia
from agents import planner_agent as pa
from lib.plan import ics, validate

NY = ZoneInfo("America/New_York")
MON = date(2026, 10, 19)


def at(day_offset, h, m=0):
    return datetime.combine(MON + timedelta(days=day_offset), time(h, m), tzinfo=NY)


FREE = [(at(i, 7), at(i, 22)) for i in range(7)]


def item(title="X", kind="workout", day=MON, start="07:00", end="07:45", **kw):
    return {"title": title, "kind": kind, "day": day, "start": start, "end": end, **kw}


def check(items):
    return validate.validate_items(items, FREE, MON, 7, time(7), time(22), NY, "")


def why(rej):
    return " ".join(" ".join(r["reasons"]) for r in rej)


class SleepAndLoad(unittest.TestCase):
    def test_workouts_must_finish_an_hour_before_waking_hours_end(self):
        self.assertEqual(len(check([item(start="20:00", end="21:00")])[0]), 1)  # ends exactly an hour before 22:00
        ok, rej = check([item(start="20:30", end="21:30")])
        self.assertEqual(ok, []); self.assertIn("bedtime", why(rej))

    def test_other_evening_activities_are_not_blocked_by_the_workout_rule(self):
        for kind in ("social", "cooking", "rest", "wellness"):
            self.assertEqual(len(check([item(kind=kind, start="20:45", end="21:45")])[0]), 1, kind)

    def test_a_day_cannot_be_overloaded(self):
        items = [item("A", "social", start="08:00", end="11:00"), item("B", "errand", start="11:30", end="14:30"), item("C", "other", start="15:00", end="16:00")]
        ok, rej = check(items)  # 3h + 3h + 1h = 7h of planned activity; the cap is 5h a day
        self.assertEqual([i["title"] for i in ok], ["A", "C"]); self.assertEqual([r["item"]["title"] for r in rej], ["B"]); self.assertIn("overload", why(rej))

    def test_rest_and_wellness_do_not_count_toward_the_daily_load(self):
        items = [item("A", "social", start="08:00", end="12:00"), item("B", "errand", start="12:30", end="13:30"), item("Rest", "rest", start="14:00", end="17:00"), item("Walk", "wellness", start="17:15", end="17:45")]
        self.assertEqual(len(check(items)[0]), 4)  # 5h of activity plus rest and a wellness break is fine (4 items is also the daily cap)


class WellnessKind(unittest.TestCase):
    def test_short_wellness_habits_are_allowed_but_not_other_short_items(self):
        ok, _ = check([item("Stretch", "wellness", start="12:00", end="12:10")])
        self.assertEqual(len(ok), 1)
        self.assertIn("Too short", why(check([item("Errand", "errand", start="12:00", end="12:10")])[1]))
        self.assertIn("Too short", why(check([item("Breathe", "wellness", start="12:00", end="12:05")])[1]))
        self.assertIn("Too long", why(check([item("Walk", "wellness", start="10:00", end="12:00")])[1]))  # habits are small, not blocks of hours

    def test_the_kind_flows_through_every_model_and_the_calendar_file(self):
        interview_routes.GoalOut(activity="Evening wind-down", kind="wellness")
        plan_routes.GoalIn(activity="Walk", kind="wellness"); plan_routes.CurrentItem(title="Walk", kind="wellness", day=MON, start="12:00", end="12:20")
        pa.ProposedItem(title="Walk", kind="wellness", day=MON, start="12:00", end="12:20"); ia.Goal(activity="Walk", kind="wellness")
        e = icalendar.Calendar.from_ical(ics.build_ics([item("Breathing break", "wellness", start="12:00", end="12:15", why="", notes="")], NY)).walk("VEVENT")[0]
        self.assertEqual([str(c) for c in e["CATEGORIES"].cats], ["Wellness"])


class Principles(unittest.TestCase):
    def test_planner_prompt_states_the_purpose_and_principles(self):
        for needle in ("busy students", "ROUTINE they can actually keep", "Consistency over intensity", "SAME time of day", "Realistic, not ambitious",
                       "Protect sleep and recovery", "at least an hour before the waking hours end", "kind `wellness`", "Nourishing, not restrictive",
                       "calories, weight loss", "Not medical advice", "qualified professional", "\"Packed\" means"):
            self.assertIn(needle, pa.PROMPT)

    def test_interview_prompt_is_aimed_at_busy_people_and_avoids_body_topics(self):
        for needle in ("busy students", "supportive coach", "commute", "exams", "Never ask about weight, body image, calories or dieting"):
            self.assertIn(needle, ia.PROMPT)


if __name__ == "__main__":
    unittest.main()
