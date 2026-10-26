"""Early (prefetch) searches: the slow web part starts before the plan step; the plan step then only does the quick
code check. Isolation per user, fallbacks, and that nothing is used for a different request."""

from __future__ import annotations

import asyncio
import unittest
from datetime import date, datetime

import plan_routes
import profile_routes
from agents import class_agent as ca
from agents import movie_agent as ma
from agents import restaurant_agent as ra
from fastapi import HTTPException
from test_calendar_and_accounts import make_user

MON = date(2026, 10, 19)


class Prefetch(unittest.TestCase):
    def setUp(self):
        self._now = plan_routes._now
        plan_routes._now = lambda tz: datetime(2026, 10, 16, 12, 0, tzinfo=tz)
        for c in (plan_routes._prefetch, plan_routes._class_cache, plan_routes._venue_cache, plan_routes._movie_cache):
            c.clear()
        self.calls = []
        self._saved = {n: getattr(plan_routes, n) for n in ("search_classes", "search_restaurants", "search_movies", "run_class_search", "run_restaurant_search", "run_movie_search", "run_planner")}

        async def s_classes(*a, **k):
            self.calls.append("search_classes"); await asyncio.sleep(0.05)
            return {"output": ca.ClassSearch(), "pages": {}, "pages_read": 1, "fetched": []}

        async def s_rest(*a, **k):
            self.calls.append("search_restaurants")
            return {"output": ra.RestaurantSearch(), "pages": {}, "pages_read": 1, "style": a[5] if len(a) > 5 else "reservation", "meal": "dinner"}

        async def s_movies(*a, **k):
            self.calls.append("search_movies")
            return {"output": ma.MovieSearch(), "pages": {}, "pages_read": 1, "where": a[1]}

        async def run_any(*a, **k):
            self.calls.append("RUN_" + str(len(a)))  # a normal (slow) search was used
            return {"classes": [], "restaurants": [], "movies": [], "counts": {}, "studios_checked": [], "unreadable": [], "pages_read": 0}

        async def fake_plan(*args, **kw):
            return {"week_start": args[7].isoformat(), "items": [], "unplaced": [], "summary": "ok"}

        plan_routes.search_classes, plan_routes.search_restaurants, plan_routes.search_movies = s_classes, s_rest, s_movies
        plan_routes.run_class_search = plan_routes.run_restaurant_search = plan_routes.run_movie_search = run_any
        plan_routes.run_planner = fake_plan

    def tearDown(self):
        plan_routes._now = self._now
        for n, f in self._saved.items():
            setattr(plan_routes, n, f)

    def user(self, name, city="New Haven, CT"):
        u, _ = make_user(name)
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York", city=city), u)
        return u

    CR = lambda self: plan_routes.ClassRequestIn(mode="new", count=1, types=["Yoga"])
    DR = lambda self: plan_routes.DinnerRequestIn(count=1, cuisines=["Italian"])
    MR = lambda self: plan_routes.MovieRequestIn(count=1, where="theater", genres=["Comedy"])

    def pre(self, u, **kw):
        return plan_routes.prefetch(plan_routes.PrefetchBody(week_start=MON, **kw), u)

    def prop(self, u, **kw):
        return plan_routes.propose(plan_routes.ProposeBody(description="xyz", week_start=MON, free=None, **kw), u)

    def test_an_early_search_is_used_by_the_plan_step_instead_of_searching_again(self):
        u = self.user("pf_a")

        async def go():
            out = await self.pre(u, class_request=self.CR(), dinner_request=self.DR(), movie_request=self.MR())
            self.assertEqual(sorted(out["started"]), ["class", "dinner", "movie"])
            r = await self.prop(u, class_request=self.CR(), dinner_request=self.DR(), movie_request=self.MR())
            return r

        r = asyncio.run(go())
        self.assertEqual(sorted(self.calls), ["search_classes", "search_movies", "search_restaurants"])  # each searched once, early
        self.assertTrue(r.class_search and r.dinner_search and r.movie_search)

    def test_asking_twice_does_not_search_twice_and_a_different_request_is_not_served_from_it(self):
        u = self.user("pf_b")

        async def go():
            await self.pre(u, class_request=self.CR())
            await self.pre(u, class_request=self.CR())
            await self.prop(u, class_request=plan_routes.ClassRequestIn(mode="new", count=1, types=["Pilates"]))  # a different request

        asyncio.run(go())
        self.assertEqual(self.calls.count("search_classes"), 1)
        self.assertEqual(self.calls.count("RUN_9"), 1)  # fell back to a normal search

    def test_a_failed_early_search_falls_back_to_a_normal_one(self):
        u = self.user("pf_c")

        async def boom(*a, **k):
            raise RuntimeError("network")

        plan_routes.search_classes = boom

        async def go():
            await self.pre(u, class_request=self.CR())
            return await self.prop(u, class_request=self.CR())

        r = asyncio.run(go())
        self.assertEqual(self.calls, ["RUN_9"]); self.assertIsNotNone(r.class_search)

    def test_an_early_search_belongs_to_one_user_only(self):
        a, b = self.user("pf_d"), self.user("pf_e")

        async def go():
            await self.pre(a, movie_request=self.MR())
            await self.prop(b, movie_request=self.MR())

        asyncio.run(go())
        self.assertEqual(self.calls.count("RUN_8"), 1)  # b searched on their own

    def test_nothing_starts_without_a_city_and_the_week_must_be_a_week_start(self):
        u = self.user("pf_f", city="")

        async def go():
            return await self.pre(u, class_request=self.CR(), dinner_request=self.DR(), movie_request=self.MR())

        self.assertEqual(asyncio.run(go())["started"], [])
        u2 = self.user("pf_g")
        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(plan_routes.prefetch(plan_routes.PrefetchBody(week_start=date(2026, 10, 20), class_request=self.CR()), u2))
        self.assertEqual(ctx.exception.status_code, 400)

    def test_home_movies_need_no_city(self):
        u = self.user("pf_h", city="")

        async def go():
            return await self.pre(u, movie_request=plan_routes.MovieRequestIn(count=1, where="home"))

        self.assertEqual(asyncio.run(go())["started"], ["movie"])


if __name__ == "__main__":
    unittest.main()
