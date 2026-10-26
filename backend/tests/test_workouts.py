"""Workouts carry specific exercises (sets, reps, rest), and the calendar file carries them (but not "why this helps")."""

from __future__ import annotations

import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import icalendar

from agents import planner_agent as pa
from lib.plan import ics, validate

NY = ZoneInfo("America/New_York")
MON = date(2026, 10, 19)
FREE = [(datetime.combine(MON + timedelta(days=i), time(7), tzinfo=NY), datetime.combine(MON + timedelta(days=i), time(22), tzinfo=NY)) for i in range(7)]
GOOD = ["Pull-ups: 3 sets of 8 reps, rest 90 seconds. Start from a full hang.", "Goblet squats: 3 sets of 12 reps, rest 60 seconds.", "Push-ups: 3 sets of 10 reps, rest 60 seconds.", "Plank: 3 x 30 seconds, rest 45 seconds."]


def item(main, **kw):
    w = {"intensity": "moderate", "equipment": ["Pull-up bar"], "warmup": ["Arm circles: 10 each way"], "main": main, "cooldown": ["Hamstring stretch: 30 seconds each leg"], "adaptation_note": ""}
    base = dict(title="Strength", kind="workout", day=MON, start="18:00", end="18:45", workout=w)
    base.update(kw)
    return base


def check(items):
    return validate.validate_items(items, FREE, MON, 7, time(7), time(22), NY)


class Rules(unittest.TestCase):
    def test_specific_exercises_are_accepted(self):
        ok, bad = check([item(GOOD)])
        self.assertEqual((len(ok), bad), (1, []))

    def test_vague_sessions_are_rejected_with_a_reason_the_planner_can_fix(self):
        for main in (["Do some squats", "Some push-ups", "Plank", "Lunges"], GOOD[:2], []):
            ok, bad = check([item(main)])
            self.assertEqual(len(ok), 0, msg=str(main)); self.assertIn("sets and reps", bad[0]["reasons"][0])

    def test_a_real_class_is_exempt_and_items_without_workout_detail_are_unchanged(self):
        ok, bad = validate.validate_items([item(["Vinyasa"], class_id="c1")], FREE, MON, 7, time(7), time(22), NY, "", None,
                                          {"c1": {"id": "c1", "title": "Flow", "studio": "S", "url": "https://x.example.com", "day": MON, "start": "18:00", "end": "18:45"}})
        self.assertEqual(bad, [])
        self.assertEqual(len(check([item(None, workout=None)])[0]), 1)

    def test_lines_are_cleaned_but_long_enough_for_a_form_cue(self):
        w = pa.Workout(main=[GOOD[0] + " " + "x" * 200])
        d = pa._clean_item(pa.ProposedItem(title="S", kind="workout", day=MON, start="18:00", end="18:45", workout=w))
        self.assertLessEqual(len(d["workout"]["main"][0]), 260); self.assertGreater(len(d["workout"]["main"][0]), 200)

    def test_the_planner_prompt_asks_for_sets_reps_and_rest(self):
        for needle in ("Pull-ups: 3 sets of 8 reps, rest 90 seconds", "sets x reps", "Every `warmup` and `cooldown` line has a count or time", "Only use equipment the user has"):
            self.assertIn(needle, pa.PROMPT)


class Calendar(unittest.TestCase):
    def test_the_event_lists_the_exercises_and_has_no_why_this_helps(self):
        ok, _ = check([item(GOOD)])
        entry = {**ok[0], "why": "", "notes": "", "benefit": {"lead": "x", "goal_link": "y", "evidence": [{"quote": "q", "source": "s", "url": "https://u.example.com", "checked": "2026-10-16"}]}}
        d = str(icalendar.Calendar.from_ical(ics.build_ics([entry], NY)).walk("VEVENT")[0]["DESCRIPTION"])
        self.assertIn("Pull-ups: 3 sets of 8 reps, rest 90 seconds", d); self.assertIn("Arm circles: 10 each way", d)
        self.assertNotIn("WHY THIS HELPS", d); self.assertNotIn("u.example.com", d)


if __name__ == "__main__":
    unittest.main()
