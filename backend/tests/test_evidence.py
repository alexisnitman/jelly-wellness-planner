"""Evidence-based "why this helps": the quotes are real and well-formed, only applicable claims are shown, the model can't
invent benefits, and the planner, page data and calendar file carry them. No network (scripts/verify_evidence.py checks the pages)."""

from __future__ import annotations

import asyncio
import json
import re
import unittest
from datetime import date, datetime, time, timedelta
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import icalendar

import plan_routes
import profile_routes
from agents import planner_agent as pa
from lib import evidence
from test_calendar_and_accounts import make_user

NY = ZoneInfo("America/New_York")
MON = date(2026, 10, 19)
ALLOWED_DOMAINS = {"medlineplus.gov", "www.nhs.uk", "www.nhlbi.nih.gov", "www.nimh.nih.gov", "www.nccih.nih.gov", "www.hsph.harvard.edu", "www.who.int", "ods.od.nih.gov"}
KINDS = {"workout", "cooking", "social", "errand", "rest", "wellness", "other"}
GOALS = {"energy", "stress", "mood", "sleep", "consistency", "fitness", "connection", "focus"}


class KnowledgeBase(unittest.TestCase):
    def test_every_claim_is_well_formed_and_from_an_authoritative_site(self):
        ids = [c["id"] for c in evidence.claims()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertGreaterEqual(len(ids), 30)
        for c in evidence.claims():
            self.assertRegex(c["id"], r"^[a-z0-9_]+$")
            self.assertTrue(set(c["kinds"]) <= KINDS and c["kinds"], c["id"])
            self.assertTrue(set(c["goals"]) <= GOALS and set(c.get("related", [])) <= GOALS, c["id"])
            self.assertIn(c["source"], json.loads(evidence.CLAIMS_PATH.read_text())["sources"], c["id"])
            u = urlparse(c["url"])
            self.assertEqual(u.scheme, "https", c["id"]); self.assertIn(u.hostname, ALLOWED_DOMAINS, c["id"])
            self.assertTrue(20 <= len(c["quote"]) <= 330, c["id"])
            self.assertNotRegex(c["quote"].lower(), r"\b(cure|guarantee|miracle|detox)\b", c["id"])

    def test_every_priority_the_user_can_pick_has_evidence_behind_it(self):
        for prio, tags in evidence.PRIORITY_TAGS.items():
            self.assertTrue(any(tags & set(c["goals"]) for c in evidence.claims()), prio)  # at least one claim whose quote itself backs this goal
        self.assertEqual(set(evidence.PRIORITIES), set(evidence.PRIORITY_TAGS))

    def test_every_activity_type_the_planner_makes_has_claims(self):
        for kind in ("workout", "cooking", "wellness", "rest", "social"):
            self.assertTrue(any(kind in c["kinds"] for c in evidence.claims()), kind)


def item(kind="workout", title="Strength session", **kw):
    base = {"title": title, "kind": kind, "notes": "", "goal": "", "end": "08:00", "recipe": None, "workout": None, "class_info": None}
    base.update(kw)
    return base


class Applicability(unittest.TestCase):
    def ok(self, cid, it):
        return evidence.applies(evidence.by_id()[cid], it)

    def test_claims_only_apply_to_the_right_kind_of_activity(self):
        self.assertTrue(self.ok("ex_energy", item()))
        self.assertFalse(self.ok("ex_energy", item("cooking", "Dinner")))
        self.assertFalse(self.ok("stay_connected", item("workout")))
        self.assertTrue(self.ok("stay_connected", item("social", "Coffee with a friend")))

    def test_activity_specific_claims_need_matching_words(self):
        self.assertTrue(self.ok("strength_muscle", item(title="Dumbbell strength session")))
        self.assertFalse(self.ok("strength_muscle", item(title="Easy yoga flow")))
        self.assertTrue(self.ok("yoga_wellness", item(title="Evening yoga")))
        self.assertFalse(self.ok("yoga_wellness", item(title="Strength session")))
        self.assertTrue(self.ok("aerobic_heart", item(title="Easy run")))
        self.assertTrue(self.ok("walk_10", item("wellness", "Fresh-air walk")))
        self.assertFalse(self.ok("breathing_stress", item("wellness", "Fresh-air walk")))
        self.assertTrue(self.ok("breathing_stress", item("wellness", "Breathing break")))
        self.assertTrue(self.ok("strength_muscle", item(workout={"equipment": ["dumbbells"], "warmup": [], "main": ["Goblet squats"], "cooldown": []}, title="Home workout")))  # found in the workout details

    def test_meal_claims_need_the_ingredient_to_really_be_in_the_recipe(self):
        oats = item("cooking", "Breakfast", recipe={"ingredients": ["1 cup rolled oats", "milk"], "steps": []})
        pasta = item("cooking", "Dinner", recipe={"ingredients": ["white pasta", "tomato sauce"], "steps": []})
        self.assertTrue(self.ok("whole_grain_steady", oats)); self.assertFalse(self.ok("whole_grain_steady", pasta))
        salmon = item("cooking", "Dinner", recipe={"ingredients": ["2 salmon fillets", "lemon"], "steps": []})
        self.assertTrue(self.ok("fish_omega3", salmon)); self.assertFalse(self.ok("fish_omega3", oats))
        veg = item("cooking", "Stir fry", recipe={"ingredients": ["broccoli", "red pepper", "tofu", "rice"], "steps": []})
        one_veg = item("cooking", "Toast", recipe={"ingredients": ["bread", "tomato"], "steps": []})
        self.assertTrue(self.ok("veg_fruit_variety", veg)); self.assertFalse(self.ok("veg_fruit_variety", one_veg))  # needs variety (2+)
        self.assertFalse(self.ok("whole_grain_steady", item("cooking", "Dinner")))  # no recipe at all
        self.assertTrue(self.ok("protein_body", veg))  # tofu

    def test_the_late_meal_claim_needs_a_late_dinner(self):
        self.assertTrue(self.ok("light_dinner_bed", item("cooking", "Dinner", end="20:30")))
        self.assertFalse(self.ok("light_dinner_bed", item("cooking", "Dinner", end="19:00")))


class Benefit(unittest.TestCase):
    def test_unknown_or_inapplicable_ids_are_dropped_and_nothing_is_claimed_without_evidence(self):
        self.assertIsNone(evidence.build_benefit(item(), ["made_up_id", "stay_connected", "yoga_wellness"], "It is great.", ["More energy"]))
        self.assertIsNone(evidence.build_benefit(item(), [], "Great for you.", ["More energy"]))
        self.assertIsNone(evidence.build_benefit(item(), None, "", None))

    def test_a_real_applicable_claim_comes_with_its_quote_source_link_and_date(self):
        b = evidence.build_benefit(item(), ["ex_energy", "ex_sleep"], "Morning exercise fits your goal of more energy.", ["More energy"])
        self.assertTrue(b["lead"].startswith("Linked to your goal of more energy"))
        ev = b["evidence"][0]
        self.assertEqual(ev["quote"], evidence.by_id()["ex_energy"]["quote"]); self.assertTrue(ev["url"].startswith("https://medlineplus.gov"))
        self.assertIn("MedlinePlus", ev["source"]); self.assertRegex(ev["checked"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertEqual(b["goal_link"], "Morning exercise fits your goal of more energy.")

    def test_only_priorities_the_cited_evidence_really_supports_are_named(self):
        b = evidence.build_benefit(item(), ["ex_energy"], "Fits your goal.", ["More energy", "Better sleep", "Focus"])
        self.assertIn("more energy", b["lead"]); self.assertNotIn("sleep", b["lead"]); self.assertNotIn("focus", b["lead"])  # ex_energy is only about energy
        g = evidence.build_benefit(item(), ["ex_energy"], "Nice.", ["Time with people"])  # no priority matched: no goal sentence, a plain lead
        self.assertEqual(g["lead"], "Why this is good for your wellbeing:"); self.assertEqual(g["goal_link"], "")

    def test_inferred_links_are_labelled_as_related_not_linked(self):
        oats = item("cooking", "Oat bowl", recipe={"ingredients": ["rolled oats", "banana"], "steps": []})
        b = evidence.build_benefit(oats, ["whole_grain_steady"], "Whole grains fit your energy goal.", ["More energy"])
        self.assertTrue(b["lead"].startswith("Related to your goal of more energy"))  # the quote says steady blood sugar, not energy
        self.assertNotIn("Linked", b["lead"])
        sleepy = evidence.build_benefit(item(), ["ex_sleep"], "Fits.", ["Better sleep"])
        self.assertTrue(sleepy["lead"].startswith("Linked to your goal of better sleep"))  # stated in the quote itself

    def test_at_most_three_claims_and_goal_matching_ones_come_first(self):
        b = evidence.build_benefit(item(), ["ex_brain", "ex_energy", "ex_sleep", "ex_mood_stress", "ex_150"], "x", ["Better sleep"])
        self.assertEqual(len(b["evidence"]), 3); self.assertEqual(b["evidence"][0]["topic"], "Exercise and sleep")

    def test_the_models_sentence_is_dropped_unless_plain(self):
        for bad in ("Cuts your risk by 40 percent.", "This will cure stress.", "Proven to boost energy.", "Prevents burnout.", "See https://x.com", "It treats anxiety.", "x" * 300, "Boosts your immune system."):
            self.assertEqual(evidence.safe_goal_link(bad), "", bad)
        self.assertEqual(evidence.safe_goal_link("A morning session fits your goal of more energy."), "A morning session fits your goal of more energy.")

    def test_the_planner_gets_the_evidence_list_with_ids_and_exact_quotes(self):
        block = evidence.evidence_block({"workout", "cooking"}, ["More energy"])
        self.assertIn('ex_energy [workout; helps: energy]', block); self.assertIn(evidence.by_id()["whole_grain_steady"]["quote"], block)
        self.assertNotIn("stay_connected", block)  # social claims aren't offered when there are no social items
        first = block.splitlines()[0]
        self.assertTrue("energy" in first)  # claims that serve the stated priority come first


def proposed(**kw):
    base = dict(title="Strength session", kind="workout", goal="workouts", day=MON, start="07:00", end="07:45", why="morning is free")
    base.update(kw)
    return pa.ProposedItem(**base)


FREE = [(datetime.combine(MON + timedelta(days=i), time(7), tzinfo=NY), datetime.combine(MON + timedelta(days=i), time(22), tzinfo=NY)) for i in range(7)]


class PlannerIntegration(unittest.TestCase):
    def run_planner(self, plan, priorities=("More energy",)):
        seen = []

        async def fake(agent, prompt, **kw):
            seen.append(prompt)
            return type("R", (), {"output": plan})()

        original = pa.run_agent
        pa.run_agent = fake
        try:
            out = asyncio.run(pa.run_planner("workouts", [{"activity": "Strength", "kind": "workout", "times_per_week": 1, "notes": ""}], [], {"city": "", "diet": "", "limits_note": ""}, "07:00", "22:00", FREE, MON, 7, NY, priorities=list(priorities)))
        finally:
            pa.run_agent = original
        return out, seen[0]

    def test_items_get_a_benefit_built_from_verified_evidence_only(self):
        out, prompt = self.run_planner(pa.ProposedPlan(items=[proposed(evidence_ids=["ex_energy", "bogus", "yoga_wellness"], goal_link="Morning exercise supports your goal of more energy.")]))
        b = out["items"][0]["benefit"]
        self.assertEqual([e["topic"] for e in b["evidence"]], ["Exercise and energy"])  # the bogus id and the yoga claim are gone
        self.assertEqual(b["goal_link"], "Morning exercise supports your goal of more energy.")
        for needle in ("THE USER'S PRIORITIES", "More energy", "EVIDENCE (the ONLY health facts", "ex_energy"):
            self.assertIn(needle, prompt)

    def test_an_item_with_no_applicable_evidence_claims_nothing(self):
        out, _ = self.run_planner(pa.ProposedPlan(items=[proposed(evidence_ids=["stay_connected"], goal_link="Great for you!")]))
        self.assertIsNone(out["items"][0]["benefit"])

    def test_a_meal_is_only_credited_for_ingredients_it_really_has(self):
        dinner = proposed(title="Oat bowl", kind="cooking", day=MON + timedelta(days=1), start="08:00", end="08:30", recipe=pa.Recipe(ingredients=["rolled oats", "banana", "blueberries"], steps=["mix"]), evidence_ids=["whole_grain_steady", "fish_omega3"])
        out, _ = self.run_planner(pa.ProposedPlan(items=[dinner]), priorities=("More energy",))
        topics = [e["topic"] for e in out["items"][0]["benefit"]["evidence"]]
        self.assertEqual(topics, ["Whole grains and steady blood sugar"])  # fish isn't in the recipe, so it isn't claimed

    def test_the_prompt_rules_forbid_inventing_benefits(self):
        for needle in ("Why each item helps", "never made up", "ONLY health facts you may rely on", "never cite an id that is not in the list", "never state a health effect that is not in a quote", "No numbers, no percentages"):
            self.assertIn(needle, pa.PROMPT)


class RoutesAndFile(unittest.TestCase):
    def setUp(self):
        self._now = plan_routes._now
        plan_routes._now = lambda tz: datetime(2026, 10, 16, 12, 0, tzinfo=tz)

    def tearDown(self):
        plan_routes._now = self._now

    def test_priorities_are_validated_and_passed_to_the_planner(self):
        self.assertEqual(plan_routes.ProposeBody(description="gym", week_start=MON, priorities=["More energy", "Hack", "More energy"]).priorities, ["More energy"])
        with self.assertRaises(ValueError):
            plan_routes.ProposeBody(description="gym", week_start=MON, priorities=["a", "b", "c", "d"])

    def test_the_calendar_file_does_not_carry_why_this_helps(self):
        user, _ = make_user("evie_x")
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York"), user)
        it = plan_routes.ExportItem(title="Strength session", kind="workout", day=MON, start="07:00", end="07:45", evidence_ids=["ex_energy"], goal_link="Fits your goal of more energy.")
        r = plan_routes.export_plan(plan_routes.ExportBody(week_start=MON, free=None, priorities=["More energy"], items=[it]), user)
        d = str(icalendar.Calendar.from_ical(r.body).walk("VEVENT")[0]["DESCRIPTION"])
        self.assertNotIn("WHY THIS HELPS", d); self.assertNotIn(evidence.by_id()["ex_energy"]["quote"], d); self.assertNotIn("medlineplus", d)

    def test_a_tampered_sentence_or_claim_cannot_reach_the_file(self):
        user, _ = make_user("finn_x")
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York"), user)
        it = plan_routes.ExportItem(title="Strength session", kind="workout", day=MON, start="07:00", end="07:45", evidence_ids=["yoga_wellness"], goal_link="This will cure all stress. Proven!")
        r = plan_routes.export_plan(plan_routes.ExportBody(week_start=MON, free=None, priorities=["Less stress"], items=[it]), user)
        d = str(icalendar.Calendar.from_ical(r.body).walk("VEVENT")[0]["DESCRIPTION"])
        self.assertNotIn("WHY THIS HELPS", d); self.assertNotIn("cure", d)  # yoga isn't a strength session; the sentence was never trusted


if __name__ == "__main__":
    unittest.main()
