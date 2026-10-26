"""Search results survive a server restart (they live in the database), stay per user and week, and expire."""

from __future__ import annotations

import time
import unittest
from datetime import date

import plan_routes
import store
from search_cache import PersistentCache
from test_calendar_and_accounts import make_user

MON = date(2026, 10, 26)


def entry(sig=("a", ("x", "y"), 2, "city")):
    out = plan_routes.DinnerSearchOut(requested=1, found=1, with_times=1, note="n", checked="2026-10-25")
    return {"at": time.time(), "sig": sig, "venues": [{"id": "r1", "name": "Pepe's", "slots": [{"day": MON, "start": "19:00", "end": "20:30"}]}], "out": out}


class Persistence(unittest.TestCase):
    def test_round_trip_keeps_dates_the_signature_tuple_and_the_summary(self):
        u, _ = make_user("sc_a")
        PersistentCache("venue", plan_routes.DinnerSearchOut)[(u["id"], MON)] = entry()
        fresh = PersistentCache("venue", plan_routes.DinnerSearchOut)  # a new object, like a restarted server
        got = fresh.get((u["id"], MON))
        self.assertEqual(got["sig"], ("a", ("x", "y"), 2, "city")); self.assertEqual(got["venues"][0]["slots"][0]["day"], MON)
        self.assertEqual(got["out"].found, 1); self.assertIsInstance(got["out"], plan_routes.DinnerSearchOut)

    def test_scoped_by_user_week_and_kind_and_pop_removes_it(self):
        a, _ = make_user("sc_b"); b, _ = make_user("sc_c")
        c = PersistentCache("venue", plan_routes.DinnerSearchOut)
        c[(a["id"], MON)] = entry()
        self.assertIsNone(c.get((b["id"], MON))); self.assertIsNone(c.get((a["id"], date(2026, 11, 2))))
        self.assertIsNone(PersistentCache("movie", plan_routes.MovieSearchOut).get((a["id"], MON)))
        self.assertIsNotNone(c.pop((a["id"], MON))); self.assertIsNone(c.get((a["id"], MON)))

    def test_old_rows_are_deleted_when_something_new_is_saved_and_clear_empties_the_kind(self):
        a, _ = make_user("sc_d")
        c = PersistentCache("venue", plan_routes.DinnerSearchOut)
        c[(a["id"], MON)] = entry()
        with store.connect() as conn:
            conn.execute("UPDATE search_cache SET saved_at = datetime('now', '-2 day')")
        c[(a["id"], date(2026, 11, 2))] = entry()
        self.assertIsNone(c.get((a["id"], MON))); self.assertIsNotNone(c.get((a["id"], date(2026, 11, 2))))
        c.clear(); self.assertIsNone(c.get((a["id"], date(2026, 11, 2))))

    def test_a_damaged_row_reads_as_no_row_and_deleting_a_user_removes_their_results(self):
        a, _ = make_user("sc_e")
        c = PersistentCache("venue", plan_routes.DinnerSearchOut)
        c[(a["id"], MON)] = entry()
        with store.connect() as conn:
            conn.execute("UPDATE search_cache SET payload = '{not json'")
        self.assertIsNone(c.get((a["id"], MON)))
        c[(a["id"], MON)] = entry()
        with store.connect() as conn:
            conn.execute("DELETE FROM users WHERE id = ?", (a["id"],))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM search_cache WHERE user_id = ?", (a["id"],)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
