"""Steps 1 and 2: the interview agent's validation and privacy, plus the multi-week calendar read for the week picker."""

from __future__ import annotations

import asyncio
import unittest
from datetime import date, timedelta

from fastapi import HTTPException

import calendar_routes
import interview_routes
import profile_routes
from agents import interview_agent as ia
from test_calendar_and_accounts import FAKE_ICS, SECRET_TITLE, make_user, req  # noqa: F401  (also sets up the temp database)
import auth
from lib.calendar import fetch


def q(**kw):
    base = dict(id="when", text="When do you like to work out?", kind="single", options=["Morning", "Evening"], why="to pick a time")
    base.update(kw)
    return ia.Question(**base)


class InterviewValidation(unittest.TestCase):
    def clean(self, *questions, goals=()):
        return ia.clean_interview(ia.Interview(goals=list(goals), questions=list(questions)))

    def test_always_three_to_five_questions(self):
        self.assertEqual(len(self.clean()["questions"]), 3)  # none from the model: gentle fallbacks
        self.assertEqual(len(self.clean(q(id="a"))["questions"]), 3)  # topped up to three
        many = [q(id=f"q{i}", text=f"Question {i}?") for i in range(9)]
        self.assertEqual(len(self.clean(*many)["questions"]), 5)  # capped at five

    def test_choice_questions_need_choices_else_become_text(self):
        out = self.clean(q(id="a", options=["Only one"]), q(id="b", kind="multi", options=[]), q(id="c", kind="text", options=["ignored", "options"]))
        kinds = {x["id"]: (x["kind"], x["options"]) for x in out["questions"]}
        self.assertEqual(kinds["a"], ("text", [])); self.assertEqual(kinds["b"], ("text", [])); self.assertEqual(kinds["c"], ("text", []))

    def test_ids_are_unique_slugs_and_text_is_bounded_and_clean(self):
        out = self.clean(q(id="Same ID!", text="A" * 500), q(id="same id!", text="Second<script>?"), q(id="", text="Third?", options=["x" * 90, "y", "y", "z", "1", "2", "3", "4"]))
        ids = [x["id"] for x in out["questions"]]
        self.assertEqual(len(ids), len(set(ids)))
        for x in out["questions"]:
            self.assertRegex(x["id"], r"^[a-z0-9_]+$")
            self.assertLessEqual(len(x["text"]), 120); self.assertNotIn("<", x["text"] + x["why"])
            self.assertLessEqual(len(x["options"]), 6); self.assertTrue(all(len(o) <= 40 for o in x["options"]))
        self.assertEqual(len(out["questions"][2]["options"]), len(set(out["questions"][2]["options"])))  # duplicates dropped

    def test_goals_are_bounded(self):
        g = [ia.Goal(activity="Lift", kind="workout", times_per_week=3, notes="n" * 500), ia.Goal(activity="", kind="rest"), ia.Goal(activity="Cook", kind="cooking", times_per_week=99)]
        out = self.clean(goals=g)["goals"]
        self.assertEqual([x["activity"] for x in out], ["Lift", "Cook"])
        self.assertEqual(out[0]["times_per_week"], 3); self.assertLessEqual(len(out[0]["notes"]), 160); self.assertIsNone(out[1]["times_per_week"])

    def test_prompt_covers_the_important_rules(self):
        for needle in ("3 to 5", "ALREADY KNOWN", "Do NOT ask", "calendar", "No medical advice", "DATA from the user"):
            self.assertIn(needle, ia.PROMPT)
        for needle in ("form", "FINAL answers", "NEVER ask again", "never fewer than 3"):  # the form choices are not asked about again
            self.assertIn(needle, ia.PROMPT)


class InterviewPrivacy(unittest.TestCase):
    def test_model_sees_flags_not_profile_text_or_identity(self):
        seen = []

        async def fake_run_agent(agent, prompt, **kw):
            seen.append((prompt, kw))
            return type("R", (), {"output": ia.Interview()})()

        original = ia.run_agent
        ia.run_agent = fake_run_agent
        try:
            asyncio.run(ia.run_interview("3 workouts and cook twice", "06:30", "23:00", True, True, True))
        finally:
            ia.run_agent = original
        prompt, kw = seen[0]
        self.assertIn("3 workouts and cook twice", prompt); self.assertIn("06:30", prompt)
        self.assertEqual(kw["feature"], "interview")
        # only yes/no flags for the sensitive profile fields; nothing else from the profile can reach it by construction
        self.assertIn("diet and allergy notes: yes", prompt); self.assertIn("city or neighborhood: yes", prompt)

    def test_route_reads_the_profile_from_the_session_and_needs_login(self):
        captured = {}

        async def fake_run(description, wake_start, wake_end, has_city, has_diet, has_limits, role_summary=""):
            captured.update(args=(description, wake_start, wake_end, has_city, has_diet, has_limits, role_summary))
            return {"goals": [], "questions": [{"id": "a", "text": "Q?", "kind": "text", "options": [], "why": ""}] * 3}

        original = interview_routes.run_interview
        interview_routes.run_interview = fake_run
        try:
            user, _ = make_user("ivan")
            profile_routes.put_profile(profile_routes.ProfileBody(wake_start="06:00", wake_end="21:00", city="Austin", diet="peanut allergy"), user)
            asyncio.run(interview_routes.questions(interview_routes.QuestionsBody(description="gym and friends"), user))
            with self.assertRaises(HTTPException) as ctx:
                auth.current_user(req(None))
            self.assertEqual(ctx.exception.status_code, 401)
        finally:
            interview_routes.run_interview = original
        self.assertEqual(captured["args"], ("gym and friends", "06:00", "21:00", True, True, False, ""))  # flags only, no text (and no role given)

    def test_ai_unavailable_becomes_a_clear_503(self):
        from lib.llm import AIUnavailable

        async def boom(*a, **k):
            raise AIUnavailable("AI features are paused today")

        original = interview_routes.run_interview
        interview_routes.run_interview = boom
        try:
            user, _ = make_user("jules")
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(interview_routes.questions(interview_routes.QuestionsBody(description="a quiet week"), user))
            self.assertEqual((ctx.exception.status_code, ctx.exception.detail), (503, "AI features are paused today"))
        finally:
            interview_routes.run_interview = original

    def test_description_limits(self):
        for bad in ("", "hi", "x" * 2001):
            with self.assertRaises(ValueError):
                interview_routes.QuestionsBody(description=bad)


class WeekPickerRange(unittest.TestCase):
    def test_reads_several_weeks_at_once(self):
        async def fake(url):
            return FAKE_ICS

        original = fetch.fetch_calendar_text
        fetch.fetch_calendar_text = fake
        try:
            user, _ = make_user("kim")
            profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York"), user)
            body = calendar_routes.ReadBody(source="file", ics_text=FAKE_ICS, week_of=date(2026, 10, 20), weeks=3)
            r = asyncio.run(calendar_routes.read_calendar(body, user))
        finally:
            fetch.fetch_calendar_text = original
        self.assertEqual((r.week_start, r.week_end, r.weeks), (date(2026, 10, 19), date(2026, 10, 19) + timedelta(days=20), 3))
        self.assertGreater(len(r.free), 14)  # free time is reported for every day in the range
        self.assertNotIn(SECRET_TITLE, r.model_dump_json())
        for bad in (0, 9):
            with self.assertRaises(ValueError):
                calendar_routes.ReadBody(source="file", ics_text=FAKE_ICS, weeks=bad)


if __name__ == "__main__":
    unittest.main()
