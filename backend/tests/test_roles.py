"""The profile asks "student, professional or other" and then role-specific follow-ups. Validation, storage, upgrade of
older databases, and how the answers reach the question agent and the planner."""

from __future__ import annotations

import asyncio
import sqlite3
import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import interview_routes
import plan_routes
import profile_routes
import store
from agents import interview_agent as ia
from agents import planner_agent as pa
from lib import roles
from test_calendar_and_accounts import make_user

STUDENT = {"level": "Undergraduate", "class_times": "Mornings", "load": "Heavy", "living": "On campus"}
PRO = {"arrangement": "Hybrid", "hours": "Standard (around 9 to 5)", "meetings": "Back-to-back", "commute": "30 to 60 minutes"}


class Spec(unittest.TestCase):
    def test_every_role_has_questions_and_the_endpoint_serves_them(self):
        spec = profile_routes.role_questions()
        self.assertEqual(set(spec), {"student", "professional", "other"})
        self.assertEqual([q.key for q in spec["student"]], ["level", "class_times", "load", "living"])
        self.assertEqual(spec["other"][0].choices, [])  # a free-text question
        for role in ("student", "professional"):
            self.assertTrue(all(len(q.choices) >= 2 for q in spec[role]))

    def test_only_valid_choices_for_the_roles_own_questions_are_kept(self):
        self.assertEqual(roles.clean_details("student", {**STUDENT, "level": "Hacker", "load": " Heavy ", "arrangement": "Hybrid", "junk": "x"}),
                         {"class_times": "Mornings", "load": "Heavy", "living": "On campus"})  # bad choice, other role's answer and unknown key all dropped
        self.assertEqual(roles.clean_details("professional", STUDENT), {})  # switching role drops the old answers
        self.assertEqual(roles.clean_details("", PRO), {})
        typical = roles.clean_details("other", {"typical": "Lab all day,\r\n<b>gym</b> at night"})["typical"]
        self.assertTrue(typical.startswith("Lab all day,")); self.assertNotIn("<", typical); self.assertNotIn("\n", typical)
        self.assertLessEqual(len(roles.clean_details("other", {"typical": "x" * 300})["typical"]), 200)
        self.assertEqual(roles.clean_details("student", {"level": 5}), {})  # not a string

    def test_the_summary_line_for_the_model(self):
        self.assertEqual(roles.describe_role("student", STUDENT), "a student: undergraduate; mornings; heavy; on campus")
        self.assertEqual(roles.describe_role("professional", {"arrangement": "Remote"}), "a working professional: remote")
        self.assertEqual(roles.describe_role("professional", {}), "a working professional")
        self.assertEqual(roles.describe_role("", {}), ""); self.assertEqual(roles.describe_role("astronaut", {}), "")
        self.assertNotIn("<", roles.describe_role("other", {"typical": "<script>"}))


class Saving(unittest.TestCase):
    def test_role_answers_round_trip_per_user_and_follow_the_role(self):
        a, _ = make_user("ruth_x"); b, _ = make_user("sid_x")
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York", role="student", role_details=STUDENT), a)
        saved = profile_routes.get_profile(a)
        self.assertEqual((saved.role, saved.role_details), ("student", STUDENT))
        self.assertEqual((profile_routes.get_profile(b).role, profile_routes.get_profile(b).role_details), ("", {}))  # not visible to others
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York", role="professional", role_details={**STUDENT, **PRO}), a)
        again = profile_routes.get_profile(a)
        self.assertEqual((again.role, again.role_details), ("professional", PRO))  # the student answers are gone

    def test_invalid_roles_are_refused(self):
        with self.assertRaises(ValueError):
            profile_routes.ProfileBody(role="wizard")
        with self.assertRaises(ValueError):
            profile_routes.ProfileBody(role_details={str(i): "x" for i in range(9)})

    def test_an_older_database_without_the_new_columns_is_upgraded(self):
        with tempfile.TemporaryDirectory() as d:
            old_dir, old_db = store.DATA_DIR, store.DB_PATH
            store.DATA_DIR, store.DB_PATH = Path(d), Path(d) / "old.db"
            try:
                conn = sqlite3.connect(store.DB_PATH)
                conn.executescript("CREATE TABLE profiles (user_id INTEGER PRIMARY KEY, wake_start TEXT NOT NULL DEFAULT '07:00', complete INTEGER NOT NULL DEFAULT 0); INSERT INTO profiles (user_id) VALUES (1);")
                conn.commit(); conn.close()
                store.init()
                with store.connect() as c:
                    cols = {r[1] for r in c.execute("PRAGMA table_info(profiles)")}
                    row = c.execute("SELECT role, role_details FROM profiles WHERE user_id = 1").fetchone()
                self.assertTrue({"role", "role_details"} <= cols); self.assertEqual((row["role"], row["role_details"]), ("", "{}"))  # existing rows keep working
            finally:
                store.DATA_DIR, store.DB_PATH = old_dir, old_db


class ReachingTheModels(unittest.TestCase):
    def test_interview_is_told_who_they_are_and_not_to_ask_again(self):
        seen = []

        async def fake(agent, prompt, **kw):
            seen.append(prompt)
            return type("R", (), {"output": ia.Interview()})()

        original = ia.run_agent
        ia.run_agent = fake
        try:
            asyncio.run(ia.run_interview("gym", "07:00", "22:00", True, False, False, roles.describe_role("student", STUDENT)))
            asyncio.run(ia.run_interview("gym", "07:00", "22:00", True, False, False))
        finally:
            ia.run_agent = original
        self.assertIn("who they are (from their profile): a student: undergraduate; mornings; heavy; on campus", seen[0])
        self.assertIn("who they are (from their profile): not given", seen[1])
        for needle in ("WHO THEY ARE", "NEVER ask about it again", "for students, think classes", "for working professionals, think meetings"):
            self.assertIn(needle.replace("NEVER", "never") if needle.startswith("NEVER") else needle, ia.PROMPT)

    def test_the_route_sends_the_saved_role_from_the_session(self):
        captured = {}

        async def fake_run(description, wake_start, wake_end, has_city, has_diet, has_limits, role_summary=""):
            captured["role"] = role_summary
            return {"goals": [], "questions": [{"id": "a", "text": "Q?", "kind": "text", "options": [], "why": ""}] * 3}

        original = interview_routes.run_interview
        interview_routes.run_interview = fake_run
        try:
            u, _ = make_user("tess_x")
            profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York", role="professional", role_details=PRO), u)
            asyncio.run(interview_routes.questions(interview_routes.QuestionsBody(description="gym and friends"), u))
        finally:
            interview_routes.run_interview = original
        self.assertEqual(captured["role"], "a working professional: hybrid; standard (around 9 to 5); back-to-back; 30 to 60 minutes")

    def test_planner_prompt_carries_who_the_user_is_and_role_guidance(self):
        seen = []

        async def fake(agent, prompt, **kw):
            seen.append(prompt)
            return type("R", (), {"output": pa.ProposedPlan()})()

        NY = ZoneInfo("America/New_York")
        original = pa.run_agent
        pa.run_agent = fake
        try:
            asyncio.run(pa.run_planner("gym", [], [], {"city": "", "diet": "", "limits_note": "", "role": "a student: undergraduate"}, "07:00", "22:00", [], date(2026, 10, 19), 7, NY))
        finally:
            pa.run_agent = original
        self.assertIn("who I am: a student: undergraduate", seen[0])
        for needle in ("For a student: protect class and study times", "For a working professional: expect meetings"):
            self.assertIn(needle, pa.PROMPT)


if __name__ == "__main__":
    unittest.main()
