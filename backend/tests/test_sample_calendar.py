"""The bundled sample calendar: anyone can try the app without their own calendar, for any week, and it carries no private data."""

from __future__ import annotations

import asyncio
import unittest
from datetime import date

import calendar_routes
import profile_routes
from test_calendar_and_accounts import make_user


class SampleCalendar(unittest.TestCase):
    def read(self, user, week):
        return asyncio.run(calendar_routes.read_calendar(calendar_routes.ReadBody(source="sample", week_of=week), user))

    def test_it_blocks_class_time_in_any_week_and_leaves_the_evenings_free(self):
        u, _ = make_user("sample_a")
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York", wake_start="07:00", wake_end="22:30"), u)
        for week in (date(2026, 10, 26), date(2027, 3, 1), date(2028, 1, 3)):
            r = self.read(u, week)
            self.assertGreaterEqual(r.events_read, 14); self.assertEqual(len([b for b in r.busy if b.start[:10] == week.isoformat()]), 3)  # Monday: two classes and a meeting
            self.assertTrue(r.free)

    def test_the_result_has_only_time_ranges_and_the_file_has_nothing_personal(self):
        u, _ = make_user("sample_b")
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="UTC"), u)
        r = self.read(u, date(2026, 10, 26))
        self.assertNotIn("Class", r.model_dump_json()); self.assertNotIn("sample", r.model_dump_json().lower())
        text = calendar_routes.SAMPLE_ICS.read_text()
        for private in ("@gmail", "@yale", "http", "LOCATION", "ATTENDEE"):
            self.assertNotIn(private, text)


if __name__ == "__main__":
    unittest.main()
