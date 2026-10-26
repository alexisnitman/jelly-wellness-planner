"""Phase 2 tests: busy/free time maths, calendar privacy, link safety and encryption, accounts and per-user isolation.

Run from backend/:   ../.venv/bin/python -m unittest discover -s tests -v
No network and no model calls (the link fetch is replaced with a fake).
"""

from __future__ import annotations

import asyncio
import json
import sys
import tempfile
import unittest
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import store  # noqa: E402

_TMP = tempfile.TemporaryDirectory()
store.DATA_DIR = Path(_TMP.name)  # never touch the real database or key in tests
store.DB_PATH = Path(_TMP.name) / "test.db"
store.init()

from fastapi import HTTPException, Request, Response  # noqa: E402

import auth  # noqa: E402
import calendar_routes  # noqa: E402
import crypto  # noqa: E402
import profile_routes  # noqa: E402
from lib.calendar import fetch, free_time, parse  # noqa: E402

NY = ZoneInfo("America/New_York")
SECRET_TITLE = "SECRET-TITLE-dentist-for-Bob"


def ics(*events: str) -> str:
    return "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//test//EN\r\n" + "".join(events) + "END:VCALENDAR\r\n"


def ev(start: str, end: str, summary=SECRET_TITLE, extra="", uid="1", allday=False) -> str:
    d = ";VALUE=DATE" if allday else ""
    return f"BEGIN:VEVENT\r\nUID:{uid}\r\nDTSTAMP:20260101T000000Z\r\nDTSTART{d}:{start}\r\nDTEND{d}:{end}\r\nSUMMARY:{summary}\r\nLOCATION:Private Place\r\nDESCRIPTION:Private notes\r\n{extra}END:VEVENT\r\n"


# the week of Mon Oct 19 2026 in New York
W0 = datetime(2026, 10, 19, tzinfo=NY)
W1 = datetime(2026, 10, 26, tzinfo=NY)


def busy(text):
    return parse.busy_ranges(text, W0, W1, NY)[0]


class BusyTime(unittest.TestCase):
    def test_timed_event_and_utc_conversion(self):
        (s, e), = busy(ics(ev("20261020T140000Z", "20261020T150000Z")))  # 14:00Z = 10:00 EDT
        self.assertEqual((s.hour, e.hour), (10, 11))

    def test_floating_time_is_read_in_the_users_zone(self):
        (s, e), = busy(ics(ev("20261020T090000", "20261020T100000")))
        self.assertEqual((s.hour, s.utcoffset()), (9, timedelta(hours=-4)))

    def test_free_and_cancelled_events_do_not_block(self):
        text = ics(ev("20261020T090000", "20261020T100000", extra="TRANSP:TRANSPARENT\r\n", uid="a"), ev("20261020T110000", "20261020T120000", extra="STATUS:CANCELLED\r\n", uid="b"))
        self.assertEqual(busy(text), [])

    def test_repeating_event_expands_into_the_week(self):
        text = ics(ev("20260105T180000", "20260105T190000", extra="RRULE:FREQ=WEEKLY;BYDAY=MO,WE\r\n"))
        days = sorted(s.date().isoformat() for s, _ in busy(text))
        self.assertEqual(days, ["2026-10-19", "2026-10-21"])

    def test_all_day_event_blocks_the_day_unless_marked_free(self):
        blocking = busy(ics(ev("20261022", "20261023", allday=True, uid="a")))
        self.assertEqual(len(blocking), 1); self.assertEqual((blocking[0][1] - blocking[0][0]), timedelta(days=1))
        self.assertEqual(busy(ics(ev("20261022", "20261023", allday=True, extra="TRANSP:TRANSPARENT\r\n", uid="b"))), [])

    def test_overlapping_events_are_merged(self):
        r = busy(ics(ev("20261020T090000", "20261020T110000", uid="a"), ev("20261020T100000", "20261020T130000", uid="b"), ev("20261020T130000", "20261020T140000", uid="c")))
        self.assertEqual(len(r), 1); self.assertEqual((r[0][0].hour, r[0][1].hour), (9, 14))

    def test_dst_change_day_keeps_wall_clock_times(self):
        # DST ends Sun Nov 1 2026 in New York
        w0, w1 = datetime(2026, 10, 26, tzinfo=NY), datetime(2026, 11, 2, tzinfo=NY)
        (s, e), = parse.busy_ranges(ics(ev("20261101T100000", "20261101T110000")), w0, w1, NY)[0]
        self.assertEqual((s.hour, s.utcoffset()), (10, timedelta(hours=-5)))

    def test_output_never_contains_event_details(self):
        r = busy(ics(ev("20261020T090000", "20261020T100000")))
        text = json.dumps([(s.isoformat(), e.isoformat()) for s, e in r])
        for secret in (SECRET_TITLE, "Private Place", "Private notes"):
            self.assertNotIn(secret, text)

    def test_garbage_is_rejected_with_a_safe_message(self):
        with self.assertRaises(parse.CalendarParseError):
            busy("this is not a calendar")


class FreeTime(unittest.TestCase):
    D = date(2026, 10, 20)

    def free(self, busy_list, **kw):
        return free_time.free_windows(busy_list, [self.D], time(7), time(22), NY, **kw)

    def at(self, h, m=0):
        return datetime(2026, 10, 20, h, m, tzinfo=NY)

    def test_empty_calendar_is_all_waking_hours(self):
        (s, e), = self.free([])
        self.assertEqual((s.hour, e.hour), (7, 22))

    def test_busy_block_splits_the_day(self):
        w = self.free([(self.at(9), self.at(10, 30))])
        self.assertEqual([(s.hour, s.minute, e.hour, e.minute) for s, e in w], [(7, 0, 9, 0), (10, 30, 22, 0)])

    def test_busy_outside_waking_hours_changes_nothing(self):
        self.assertEqual(len(self.free([(self.at(2), self.at(6)), (self.at(23), self.at(23, 30))])), 1)

    def test_busy_across_the_edges_is_clipped(self):
        w = self.free([(self.at(5), self.at(8)), (self.at(21), self.at(23))])
        self.assertEqual([(s.hour, e.hour) for s, e in w], [(8, 21)])

    def test_short_gaps_are_dropped(self):
        w = self.free([(self.at(9), self.at(12)), (self.at(12, 20), self.at(22))])
        self.assertEqual([(s.hour, e.hour) for s, e in w], [(7, 9)])  # the 20-minute gap is too short to use

    def test_fully_busy_day_has_no_free_time(self):
        self.assertEqual(self.free([(self.at(0), self.at(23, 59))]), [])

    def test_week_bounds_follow_the_users_week_start(self):
        self.assertEqual(free_time.week_bounds(date(2026, 10, 22), 0)[0], date(2026, 10, 19))  # Monday start
        self.assertEqual(free_time.week_bounds(date(2026, 10, 22), 6)[0], date(2026, 10, 18))  # Sunday start
        self.assertEqual(free_time.week_bounds(date(2026, 10, 19), 0), (date(2026, 10, 19), date(2026, 10, 26)))


class LinkSafety(unittest.TestCase):
    def test_link_rules(self):
        self.assertEqual(fetch.normalize_link("webcal://cal.example.com/x.ics"), "https://cal.example.com/x.ics")
        for bad in ("http://cal.example.com/x.ics", "ftp://x.com/a", "file:///etc/passwd", "javascript:alert(1)", "https://user:pw@cal.example.com/x", "not a url"):
            with self.assertRaises(fetch.CalendarFetchError):
                fetch.normalize_link(bad)

    def test_private_and_local_addresses_are_never_fetched(self):
        for host in ("localhost", "127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "0.0.0.0", "::1"):
            self.assertFalse(fetch.public_host(host), host)
        secret = "https://127.0.0.1/private-token-12345.ics"
        with self.assertRaises(fetch.CalendarFetchError) as ctx:
            asyncio.run(fetch.fetch_calendar_text(secret))
        self.assertNotIn("private-token-12345", str(ctx.exception))  # errors never echo the link

    def test_encryption_round_trip_and_ciphertext_is_opaque(self):
        crypto.reset_cache()
        url = "https://cal.example.com/private-token-abc123.ics"
        token = crypto.encrypt(url)
        self.assertNotIn("abc123", token); self.assertNotIn("cal.example.com", token)
        self.assertEqual(crypto.decrypt(token), url)
        self.assertIsNone(crypto.decrypt("not-a-valid-token"))
        self.assertEqual((store.DATA_DIR / "app.key").stat().st_mode & 0o777, 0o600)


class ProfileRules(unittest.TestCase):
    def test_waking_hours_must_make_sense(self):
        profile_routes.ProfileBody(wake_start="06:30", wake_end="23:00", timezone="America/New_York")
        for kw in (dict(wake_start="22:00", wake_end="07:00"), dict(wake_start="07:00", wake_end="07:00"), dict(wake_start="07:00", wake_end="08:00"), dict(wake_start="7am"), dict(timezone="Mars/Olympus"), dict(week_start=7)):
            with self.assertRaises(ValueError, msg=str(kw)):
                profile_routes.ProfileBody(**kw)


def req(cookie=None) -> Request:
    headers = [(b"cookie", f"session={cookie}".encode())] if cookie else []
    return Request({"type": "http", "headers": headers, "client": ("127.0.0.1", 1)})


def make_user(name):
    resp = Response()
    auth.register(auth.RegisterBody(first_name=name, email=f"{name}@x.com", username=name, password=f"password-for-{name}"), resp)
    token = resp.headers["set-cookie"].split("session=")[1].split(";")[0]
    return auth.current_user(req(token)), token


FAKE_ICS = ics(ev("20261020T090000", "20261020T100000"))


class AccountsAndIsolation(unittest.TestCase):
    def setUp(self):
        self._orig = fetch.fetch_calendar_text
        async def fake(url):  # no network in tests
            return FAKE_ICS
        fetch.fetch_calendar_text = fake
        crypto.reset_cache()

    def tearDown(self):
        fetch.fetch_calendar_text = self._orig

    def read(self, user, **kw):
        body = calendar_routes.ReadBody(week_of=date(2026, 10, 20), **kw)
        return asyncio.run(calendar_routes.read_calendar(body, user))

    def test_profiles_are_isolated_per_user(self):
        alice, atok = make_user("alice"); bob, btok = make_user("bob")
        profile_routes.put_profile(profile_routes.ProfileBody(wake_start="06:00", wake_end="21:00", city="Austin", diet="peanut allergy"), alice)
        self.assertEqual(profile_routes.get_profile(auth.current_user(req(btok))).city, "")
        self.assertEqual(profile_routes.get_profile(auth.current_user(req(atok))).diet, "peanut allergy")

    def test_no_session_or_forged_session_is_refused(self):
        for cookie in (None, "forged", "x" * 43):
            with self.assertRaises(HTTPException) as ctx:
                auth.current_user(req(cookie))
            self.assertEqual(ctx.exception.status_code, 401)

    def test_passwords_and_session_tokens_are_not_stored_in_plain_text(self):
        _, token = make_user("carol")
        with store.connect() as conn:
            pw = conn.execute("SELECT password_hash FROM users WHERE username='carol'").fetchone()[0]
            hashes = [r[0] for r in conn.execute("SELECT token_hash FROM sessions")]
        self.assertTrue(pw.startswith("$argon2id$")); self.assertNotIn("password-for-carol", pw); self.assertNotIn(token, hashes)

    def test_login_errors_do_not_reveal_whether_a_username_exists(self):
        make_user("dave")
        msgs = set()
        for u, p in (("dave", "wrong-password-1"), ("nobody-here", "whatever-pass-1")):
            with self.assertRaises(HTTPException) as ctx:
                auth.login(auth.LoginBody(username=u, password=p), req(), Response())
            msgs.add((ctx.exception.status_code, ctx.exception.detail))
        self.assertEqual(len(msgs), 1)

    def test_calendar_needs_a_saved_profile_first(self):
        erin, _ = make_user("erin")
        with self.assertRaises(HTTPException) as ctx:
            self.read(erin, source="file", ics_text=FAKE_ICS)
        self.assertEqual(ctx.exception.status_code, 409)

    def test_reading_a_file_returns_only_ranges_and_stores_nothing(self):
        frank, _ = make_user("frank")
        profile_routes.put_profile(profile_routes.ProfileBody(wake_start="07:00", wake_end="22:00", timezone="America/New_York"), frank)
        result = self.read(frank, source="file", ics_text=FAKE_ICS)
        dumped = result.model_dump_json()
        for secret in (SECRET_TITLE, "Private Place", "Private notes"):
            self.assertNotIn(secret, dumped)
        self.assertEqual(result.events_read, 1); self.assertEqual(len(result.busy), 1)
        self.assertFalse(result.link.saved)
        with store.connect() as conn:  # the uploaded file is not kept anywhere
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM calendar_links WHERE user_id=?", (frank["id"],)).fetchone()[0], 0)

    def test_remembered_link_is_encrypted_hidden_isolated_and_forgettable(self):
        gina, _ = make_user("gina"); hal, _ = make_user("hal")
        for u in (gina, hal):
            profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York"), u)
        link = "https://calendar.example.com/ical/private-token-zzz999/basic.ics"
        r = self.read(gina, source="link", url=link, remember=True)
        self.assertTrue(r.link.saved); self.assertEqual(r.link.host, "calendar.example.com")
        self.assertNotIn("zzz999", r.model_dump_json())  # the link is never sent back
        with store.connect() as conn:
            row = conn.execute("SELECT url_enc, host FROM calendar_links WHERE user_id=?", (gina["id"],)).fetchone()
        self.assertNotIn("zzz999", row["url_enc"]); self.assertNotIn("private-token", row["url_enc"])
        self.assertFalse(calendar_routes.link_status(hal).saved)  # other users can't see it
        with self.assertRaises(HTTPException):  # ...or use it
            self.read(hal, source="saved")
        self.assertEqual(len(self.read(gina, source="saved").busy), 1)  # the saved link works for its owner
        calendar_routes.forget_link(gina)
        self.assertFalse(calendar_routes.link_status(gina).saved)

    def test_link_is_not_remembered_unless_asked(self):
        ivy, _ = make_user("ivy")
        profile_routes.put_profile(profile_routes.ProfileBody(timezone="America/New_York"), ivy)
        self.assertFalse(self.read(ivy, source="link", url="https://calendar.example.com/x.ics", remember=False).link.saved)


if __name__ == "__main__":
    unittest.main()
