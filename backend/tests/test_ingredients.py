"""Ingredients the user wants to use: cleaning, the planner prompt, and a plain report of any that no recipe used."""

from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import plan_routes
from agents import planner_agent as pa

NY = ZoneInfo("America/New_York")
MON = date(2026, 10, 19)
FREE = [(datetime.combine(MON + timedelta(days=i), time(7), tzinfo=NY), datetime.combine(MON + timedelta(days=i), time(22), tzinfo=NY)) for i in range(7)]


def run(ingredients, recipe_lines):
    calls = []
    item = pa.ProposedItem(title="Veggie curry", kind="cooking", day=MON, start="18:00", end="19:00", recipe=pa.Recipe(ingredients=recipe_lines, steps=["Cook it."]))

    async def fake(agent, prompt, **kw):
        calls.append(prompt)
        return type("R", (), {"output": pa.ProposedPlan(items=[item])})()

    original = pa.run_agent
    pa.run_agent = fake
    try:
        out = asyncio.run(pa.run_planner("cook", [], [], {"city": "", "diet": "", "limits_note": ""}, "07:00", "22:00", FREE, MON, 7, NY, ingredients=ingredients))
    finally:
        pa.run_agent = original
    return out, calls


class Ingredients(unittest.TestCase):
    def test_request_cleans_dedupes_and_limits(self):
        b = plan_routes.ProposeBody(description="cook", week_start=MON, ingredients=["  spinach ", "Spinach\n", "", "sweet  potatoes"])
        self.assertEqual(b.ingredients, ["spinach", "Spinach", "sweet potatoes"])
        self.assertNotIn("", b.ingredients); self.assertTrue(all("\n" not in i for i in b.ingredients))
        with self.assertRaises(ValueError):
            plan_routes.ProposeBody(description="cook", week_start=MON, ingredients=["x"] * 9)

    def test_the_prompt_lists_them_and_puts_diet_first(self):
        _, calls = run(["spinach", "chickpeas"], ["1 can chickpeas", "2 cups spinach"])
        self.assertIn("INGREDIENTS THE USER WANTS TO USE", calls[0]); self.assertIn("spinach, chickpeas", calls[0]); self.assertIn("Diet and allergy notes still come first", calls[0])
        _, none = run([], ["1 can chickpeas"])
        self.assertNotIn("INGREDIENTS THE USER WANTS", none[0])

    def test_unused_ingredients_are_reported_and_used_ones_match_plurals(self):
        out, _ = run(["chickpeas", "sweet potato", "mango", "sweet potatoes", "berries"], ["1 can chickpea", "2 sweet potatoes", "1 cup berry compote", "1 tbsp oil"])
        titles = [u["title"] for u in out["unplaced"]]
        self.assertEqual(titles, ["Ingredient not used: mango"])

    def test_prompt_rules(self):
        for needle in ("INGREDIENTS THE USER WANTS TO USE", "grocery shopping", "BEFORE the first cooked meal"):
            self.assertIn(needle, pa.PROMPT)


if __name__ == "__main__":
    unittest.main()
