"""Step 4: plan validation in code, the diet/allergy cross-check, the planner's repair loop and privacy, and the route."""

from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException

import plan_routes
import profile_routes
from agents import planner_agent as pa
from lib.llm import AIUnavailable
from lib.plan import diet, validate
from test_calendar_and_accounts import make_user

NY = ZoneInfo("America/New_York")
MON = date(2026, 10, 19)


def at(day_offset, h, m=0):
    return datetime.combine(MON + timedelta(days=day_offset), time(h, m), tzinfo=NY)


# free: Monday 07:00-09:00 and 10:30-22:00, Tuesday 07:00-22:00
FREE = [(at(0, 7), at(0, 9)), (at(0, 10, 30), at(0, 22)), (at(1, 7), at(1, 22))]


def item(title="Run", kind="workout", day=MON, start="07:30", end="08:15", **kw):
    return {"title": title, "kind": kind, "day": day, "start": start, "end": end, **kw}


def check(items, notes="", free=FREE):
    return validate.validate_items(items, free, MON, 7, time(7), time(22), NY, notes)


def reasons(rej):
    return " ".join(" ".join(r["reasons"]) for r in rej)


class Validation(unittest.TestCase):
    def test_item_inside_a_free_window_is_accepted_with_offset_times(self):
        ok, rej = check([item()])
        self.assertEqual((len(ok), len(rej)), (1, 0))
        self.assertEqual(ok[0]["start_iso"], "2026-10-19T07:30:00-04:00")

    def test_item_overlapping_a_busy_time_is_rejected(self):
        ok, rej = check([item(start="08:30", end="09:30")])  # 09:00-10:30 is busy
        self.assertEqual(ok, []); self.assertIn("free time window", reasons(rej))
        self.assertEqual(check([item(start="09:00", end="09:45")])[0], [])  # starting at the busy block's start is also not free

    def test_item_must_fit_inside_one_window_not_span_two(self):
        self.assertEqual(check([item(start="08:30", end="11:00")])[0], [])

    def test_waking_hours_week_and_time_format(self):
        free_all = [(at(1, 0), at(1, 23, 59))]
        ok, rej = check([item(day=MON + timedelta(days=1), start="06:00", end="06:45")], free=free_all)
        self.assertIn("waking hours", reasons(rej))
        self.assertIn("outside the chosen week", reasons(check([item(day=MON + timedelta(days=9))], free=free_all)[1]))
        for bad in ("7:30", "25:00", "noon", ""):
            self.assertIn("look like", reasons(check([item(start=bad, end="08:00")])[1]), bad)

    def test_lengths(self):
        self.assertIn("Too short", reasons(check([item(start="07:30", end="07:40")])[1]))
        self.assertIn("Too short", reasons(check([item(start="08:00", end="07:30")])[1]))  # end before start
        self.assertIn("Too long", reasons(check([item(start="11:00", end="14:00")])[1]))  # a 3 hour workout

    def test_buffer_and_overlap_between_items(self):
        ok, rej = check([item("A", start="07:00", end="07:45"), item("B", start="07:50", end="08:30")])  # 5 minute gap
        self.assertEqual([i["title"] for i in ok], ["A"]); self.assertIn("15 minutes", reasons(rej))
        ok, _ = check([item("A", start="07:00", end="07:45"), item("B", start="08:00", end="08:40")])  # exactly 15
        self.assertEqual(len(ok), 2)
        ok, rej = check([item("A", start="11:00", end="12:00"), item("B", start="11:30", end="12:30")])
        self.assertEqual(len(ok), 1)

    def test_at_most_four_items_a_day(self):
        items = [item(f"I{n}", kind="errand", day=MON + timedelta(days=1), start=f"{8 + 2 * n:02d}:00", end=f"{8 + 2 * n:02d}:30") for n in range(5)]
        ok, rej = check(items)
        self.assertEqual((len(ok), len(rej)), (4, 1)); self.assertIn("Too many", reasons(rej))

    def test_recipe_that_conflicts_with_allergy_or_diet_is_rejected(self):
        dinner = lambda ing: item("Dinner", "cooking", day=MON + timedelta(days=1), start="18:00", end="19:30", recipe={"ingredients": ing})
        self.assertEqual(check([dinner(["2 tbsp peanut oil", "rice"])], notes="severe peanut allergy")[0], [])
        self.assertIn("peanut", reasons(check([dinner(["peanut sauce"])], notes="peanut allergy")[1]))
        self.assertEqual(check([dinner(["chicken breast", "rice"])], notes="vegetarian")[0], [])
        self.assertEqual(check([dinner(["honey glaze", "tofu"])], notes="vegan")[0], [])
        self.assertEqual(len(check([dinner(["peanut sauce", "chicken"])], notes="")[0]), 1)  # no notes: nothing to conflict with
        self.assertEqual(len(check([dinner(["chickpeas", "rice", "olive oil"])], notes="vegetarian, peanut allergy")[0]), 1)  # no false alarm


class Diet(unittest.TestCase):
    def test_notes_are_read_conservatively(self):
        labels = lambda n: [l for l, _ in diet.avoid_list(n)]
        self.assertIn("peanut", labels("Peanut allergy")); self.assertIn("dairy", labels("lactose intolerant"))
        self.assertIn("wheat/gluten", labels("celiac")); self.assertIn("sesame", labels("allergic to sesame"))
        self.assertIn("pork", labels("no pork")); self.assertEqual(labels("I like running"), [])

    def test_matches_whole_words_not_fragments(self):
        self.assertEqual(diet.recipe_conflicts(["2 cloves minced garlic", "1 bunch cilantro", "butternut squash"], "vegetarian, wheat allergy, dairy-free"), [])
        self.assertTrue(diet.recipe_conflicts(["1/2 cup peanuts"], "peanut allergy"))  # plurals still match
        self.assertTrue(diet.recipe_conflicts(["2 eggs"], "egg allergy")); self.assertTrue(diet.recipe_conflicts(["minced beef"], "vegetarian"))

    def test_pescatarian_allows_fish_but_vegetarian_does_not(self):
        self.assertEqual(diet.recipe_conflicts(["salmon fillet"], "pescatarian"), [])
        self.assertTrue(diet.recipe_conflicts(["salmon fillet"], "vegetarian"))
        self.assertTrue(diet.recipe_conflicts(["pesto"], "tree nut allergy"))  # hidden nuts


def proposed(**kw):
    base = dict(title="Strength", kind="workout", goal="workouts", day=MON, start="07:30", end="08:15", why="morning is free")
    base.update(kw)
    return pa.ProposedItem(**base)


class Planner(unittest.TestCase):
    def run_planner(self, responses, notes=None):
        calls = []

        async def fake(agent, prompt, **kw):
            calls.append((prompt, kw))
            r = responses[min(len(calls) - 1, len(responses) - 1)]
            if isinstance(r, Exception):
                raise r
            return type("R", (), {"output": r})()

        original = pa.run_agent
        pa.run_agent = fake
        try:
            out = asyncio.run(pa.run_planner("3 workouts and cook twice", [{"activity": "Strength", "kind": "workout", "times_per_week": 3, "notes": ""}], [{"question": "When?", "answer": "Mornings"}],
                                             notes or {"city": "Austin, TX", "diet": "peanut allergy", "limits_note": "sore left knee"}, "07:00", "22:00", FREE, MON, 7, NY))
        finally:
            pa.run_agent = original
        return out, calls

    def test_prompt_carries_notes_and_free_time_but_no_calendar_details(self):
        _, calls = self.run_planner([pa.ProposedPlan(items=[proposed()], summary="ok")])
        prompt = calls[0][0]
        for needle in ("peanut allergy", "sore left knee", "Austin, TX", "FREE TIME", "Monday 2026-10-19: 07:00-09:00, 10:30-22:00", "Mornings"):
            self.assertIn(needle, prompt)
        self.assertNotIn("busy", prompt.lower().split("evidence (")[0]); self.assertEqual(calls[0][1]["feature"], "planner")  # (the evidence quotes themselves mention "busy people")

    def test_items_in_the_past_are_rejected_with_a_clear_reason(self):
        ok, rej = validate.validate_items([item(start="07:30", end="08:15")], FREE, MON, 7, time(7), time(22), NY, "", at(0, 12))
        self.assertEqual(ok, []); self.assertIn("already passed", reasons(rej))

    def test_valid_plan_needs_no_repair_call(self):
        out, calls = self.run_planner([pa.ProposedPlan(items=[proposed()], summary="A calm week.")])
        self.assertEqual(len(calls), 1); self.assertEqual(len(out["items"]), 1); self.assertEqual(out["items"][0]["id"], "item1")

    def test_rejected_items_get_one_repair_attempt(self):
        bad = proposed(title="Late run", start="08:30", end="09:30")  # on top of a busy block
        fixed = proposed(title="Late run", start="11:00", end="11:45")
        out, calls = self.run_planner([pa.ProposedPlan(items=[proposed(), bad]), pa.ProposedPlan(items=[fixed])])
        self.assertEqual(len(calls), 2); self.assertIn("REPAIR", calls[1][0]); self.assertEqual(calls[1][1]["feature"], "planner_repair")
        self.assertEqual(sorted(i["title"] for i in out["items"]), ["Late run", "Strength"]); self.assertEqual(out["unplaced"], [])

    def test_items_that_still_fail_go_to_unplaced_never_into_the_plan(self):
        bad = proposed(title="Impossible", start="08:30", end="09:30")
        out, calls = self.run_planner([pa.ProposedPlan(items=[bad]), pa.ProposedPlan(items=[bad])])
        self.assertEqual(out["items"], []); self.assertEqual(len(calls), 2)
        self.assertEqual(out["unplaced"][0]["title"], "Impossible"); self.assertIn("free time", out["unplaced"][0]["reason"])

    def test_a_failed_repair_call_keeps_the_first_result(self):
        out, _ = self.run_planner([pa.ProposedPlan(items=[proposed(), proposed(title="Bad", start="08:30", end="09:30")]), RuntimeError("boom")])
        self.assertEqual([i["title"] for i in out["items"]], ["Strength"]); self.assertEqual(out["unplaced"][0]["title"], "Bad")

    def test_a_recipe_with_the_users_allergen_is_dropped(self):
        dinner = proposed(title="Pad thai night", kind="cooking", day=MON + timedelta(days=1), start="18:00", end="19:30", recipe=pa.Recipe(ingredients=["rice noodles", "crushed peanuts"], steps=["cook"]))
        out, _ = self.run_planner([pa.ProposedPlan(items=[dinner]), pa.ProposedPlan(items=[])])
        self.assertEqual(out["items"], []); self.assertIn("peanut", out["unplaced"][0]["reason"])

    def test_text_is_cleaned_links_removed_and_safe_scrubbed(self):
        plan = pa.ProposedPlan(items=[proposed(notes="Try https://evil.example/run <b>now</b>", why="This is a safe workout")], summary="A totally safe week")
        out, _ = self.run_planner([plan])
        self.assertNotIn("http", out["items"][0]["notes"]); self.assertNotIn("<", out["items"][0]["notes"])
        self.assertNotRegex(out["summary"].lower(), r"\bsafe")

    def test_recipe_and_workout_details_only_on_matching_kinds(self):
        out, _ = self.run_planner([pa.ProposedPlan(items=[proposed(recipe=pa.Recipe(ingredients=["x"]), workout=pa.Workout(main=["Squats: 3 sets of 10 reps, rest 60 seconds", "Push-ups: 3 sets of 8 reps, rest 60 seconds", "Plank: 3 x 30 seconds, rest 45 seconds"]))])])
        self.assertIsNone(out["items"][0]["recipe"]); self.assertEqual(out["items"][0]["workout"]["main"][0], "Squats: 3 sets of 10 reps, rest 60 seconds")

    def test_revision_prompt_carries_the_change_request_the_current_plan_and_removed_items(self):
        rev = {"feedback": "Move workouts to mornings and swap Thai for something else", "current": [{"title": "Home strength", "kind": "workout", "day": "2026-10-19", "start": "18:00", "end": "18:45"}], "removed": ["Thai dinner"]}
        calls = []

        async def fake(agent, prompt, **kw):
            calls.append(prompt)
            return type("R", (), {"output": pa.ProposedPlan(items=[proposed()], summary="ok")})()

        original = pa.run_agent
        pa.run_agent = fake
        try:
            asyncio.run(pa.run_planner("x" * 5, [], [], {"city": "", "diet": "", "limits_note": ""}, "07:00", "22:00", FREE, MON, 7, NY, revision=rev))
            asyncio.run(pa.run_planner("x" * 5, [], [], {"city": "", "diet": "", "limits_note": ""}, "07:00", "22:00", FREE, MON, 7, NY))
        finally:
            pa.run_agent = original
        for needle in ("REVISION", "Move workouts to mornings", "Home strength (workout, 2026-10-19 18:00-18:45)", "REMOVED BY THE USER", "Thai dinner"):
            self.assertIn(needle, calls[0])
        self.assertNotIn("REVISION", calls[1])  # a first plan has no revision section
        for needle in ("REVISION", "CHANGE REQUEST", "never bring back removed items", "can never override the diet and allergy notes"):
            self.assertIn(needle, pa.PROMPT)

    def test_prompt_file_has_the_rules(self):
        for needle in ("ONLY times you may use", "15 minutes", "Do NOT name specific restaurants", "STRICTLY", "not medical advice", "injury or limit notes", "DATA written by the user", "explicit choices from a form"):
            self.assertIn(needle, pa.PROMPT)


class PlanRoute(unittest.TestCase):
    def setUp(self):
        self._now = plan_routes._now
        plan_routes._now = lambda tz: datetime(2026, 10, 16, 12, 0, tzinfo=tz)  # pin the clock: Fri Oct 16 2026, noon

    def tearDown(self):
        plan_routes._now = self._now

    def propose(self, user, free="default", week=MON, **kw):
        captured = {}

        async def fake(*args, **kw):
            captured["args"] = args
            return {"week_start": args[7].isoformat(), "items": [], "unplaced": [], "summary": "ok"}

        original = plan_routes.run_planner
        plan_routes.run_planner = fake
        try:
            body = plan_routes.ProposeBody(description="gym and friends", week_start=week, free=None if free is None else ([] if free == "default" else free), **kw)
            result = asyncio.run(plan_routes.propose(body, user))
        finally:
            plan_routes.run_planner = original
        return result, captured.get("args")

    def make(self, name, **profile):
        user, _ = make_user(name)
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York", **profile), user)
        return user

    def test_profile_notes_come_from_the_session_not_the_request(self):
        user = self.make("lena", wake_start="06:00", wake_end="21:00", city="Austin", diet="peanut allergy", limits_note="sore knee")
        _, args = self.propose(user)
        self.assertEqual(args[3], {"city": "Austin", "diet": "peanut allergy", "limits_note": "sore knee", "role": ""}); self.assertEqual((args[4], args[5]), ("06:00", "21:00"))
        self.assertNotIn("first_name", str(args)); self.assertNotIn("lena@x.com", str(args))

    def test_no_calendar_means_free_during_waking_hours(self):
        user = self.make("moe_x", wake_start="08:00", wake_end="20:00")
        result, args = self.propose(user, free=None)
        free = args[6]
        self.assertEqual(len(free), 7); self.assertEqual((free[0][0].hour, free[0][1].hour), (8, 20)); self.assertFalse(result.used_calendar)

    def test_client_free_windows_are_clipped_to_waking_hours(self):
        user = self.make("nia", wake_start="08:00", wake_end="20:00")
        spans = [plan_routes.SpanIn(start=at(0, 6), end=at(0, 23)), plan_routes.SpanIn(start=at(1, 12), end=at(1, 12, 10))]
        _, args = self.propose(user, free=spans)
        free = args[6]
        self.assertEqual(len(free), 1)  # the 10 minute sliver is dropped
        self.assertEqual((free[0][0].hour, free[0][1].hour), (8, 20))

    def test_the_past_is_never_offered_to_the_planner(self):
        user = self.make("rae_x", wake_start="08:00", wake_end="20:00")
        _, args = self.propose(user, free=None, week=date(2026, 10, 12))  # the week already in progress
        free = args[6]
        self.assertTrue(all(a >= datetime(2026, 10, 16, 12, tzinfo=NY) for a, _ in free))  # nothing before "now"
        self.assertEqual([a.date().isoformat() for a, _ in free], ["2026-10-16", "2026-10-17", "2026-10-18"])
        self.assertEqual((free[0][0].hour, free[0][1].hour), (12, 20))  # today starts at the current time

    def test_week_must_start_on_the_users_week_start_day(self):
        user = self.make("omar")
        with self.assertRaises(HTTPException) as ctx:
            self.propose(user, week=MON + timedelta(days=2))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_incomplete_profile_is_refused_and_ai_pause_is_a_503(self):
        fresh, _ = make_user("pia")
        with self.assertRaises(HTTPException) as ctx:
            self.propose(fresh)
        self.assertEqual(ctx.exception.status_code, 409)
        user = self.make("quin")

        async def boom(*a, **k):
            raise AIUnavailable("AI features are paused today")

        original = plan_routes.run_planner
        plan_routes.run_planner = boom
        try:
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(plan_routes.propose(plan_routes.ProposeBody(description="gym time", week_start=MON, free=None), user))
            self.assertEqual((ctx.exception.status_code, ctx.exception.detail), (503, "AI features are paused today"))
        finally:
            plan_routes.run_planner = original

    def test_the_change_request_reaches_the_planner_cleaned_and_bounded(self):
        user = self.make("sol_x")
        captured = {}

        async def fake(*args, **kw):
            captured["rev"] = kw.get("revision")
            return {"week_start": args[7].isoformat(), "items": [], "unplaced": [], "summary": "ok"}

        original = plan_routes.run_planner
        plan_routes.run_planner = fake
        try:
            body = plan_routes.ProposeBody(description="gym time", week_start=MON, free=None, feedback="Mornings please\x00 https://evil.example",
                                           current=[plan_routes.CurrentItem(title="Run\r\nINJECT", kind="workout", day=MON, start="07:00", end="07:45")], removed=["Thai dinner"])
            asyncio.run(plan_routes.propose(body, user))
            rev = captured["rev"]
            asyncio.run(plan_routes.propose(plan_routes.ProposeBody(description="gym time", week_start=MON, free=None), user))
            self.assertIsNone(captured["rev"])  # a first plan has no revision
        finally:
            plan_routes.run_planner = original
        self.assertNotIn("\x00", rev["feedback"]); self.assertEqual(rev["current"][0]["title"], "Run INJECT"); self.assertEqual(rev["removed"], ["Thai dinner"])

    def test_request_limits(self):
        for kw in (dict(description="x"), dict(description="gym", goals=[{"activity": "a"}] * 13), dict(description="gym", answers=[{"question": "q", "answer": "a"}] * 11), dict(description="gym", feedback="x" * 601), dict(description="gym", removed=["a"] * 21)):
            with self.assertRaises(ValueError):
                plan_routes.ProposeBody(week_start=MON, **kw)


if __name__ == "__main__":
    unittest.main()
