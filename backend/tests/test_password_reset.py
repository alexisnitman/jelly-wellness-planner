"""Forgotten password: the same answer for every email, a one-use 30-minute link (local mode: printed in the backend
terminal), only a hash stored, old sessions and old links die, throttling, and nothing sensitive in the output."""

from __future__ import annotations

import contextlib
import io
import unittest
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException, Request, Response

import auth
import store
from test_calendar_and_accounts import make_user, req


def request(ip="9.9.9.9") -> Request:
    return Request({"type": "http", "headers": [], "client": (ip, 1)})


def login(username, password):
    return auth.login(auth.LoginBody(username=username, password=password), request(), Response())


class Reset(unittest.TestCase):
    def setUp(self):
        auth._fails.clear()
        self.links = []
        self._deliver = auth.reset_delivery.deliver
        auth.reset_delivery.deliver = lambda username, link: self.links.append((username, link))

    def tearDown(self):
        auth.reset_delivery.deliver = self._deliver

    def forgot(self, email, ip="9.9.9.9"):
        return auth.forgot(auth.ForgotBody(email=email), request(ip))

    def token(self):
        return self.links[-1][1].split("reset=")[1]

    def reset(self, token, password="a brand new password 42"):
        return auth.reset(auth.ResetBody(token=token, password=password), request())

    def test_the_answer_is_identical_for_known_and_unknown_emails_and_only_known_ones_get_a_link(self):
        make_user("rp_a")
        known, unknown = self.forgot("rp_a@x.com"), self.forgot("nobody@x.com")
        self.assertEqual(known, unknown)
        self.assertEqual(len(self.links), 1); self.assertEqual(self.links[0][0], "rp_a"); self.assertTrue(self.links[0][1].startswith("http://localhost:5200/?reset="))

    def test_only_a_hash_of_the_token_is_stored_and_it_expires_in_30_minutes(self):
        u, _ = make_user("rp_b")
        self.forgot("rp_b@x.com")
        tok = self.token()
        with store.connect() as c:
            rows = c.execute("SELECT * FROM password_resets WHERE user_id = ?", (u["id"],)).fetchall()
        self.assertEqual(len(rows), 1); self.assertNotIn(tok, str(dict(rows[0]))); self.assertEqual(rows[0]["token_hash"], auth._hash_token(tok))
        left = datetime.strptime(rows[0]["expires_at"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc) - datetime.now(timezone.utc)
        self.assertTrue(timedelta(minutes=28) < left <= timedelta(minutes=30))

    def test_the_new_password_works_the_old_one_does_not_and_the_link_works_once(self):
        make_user("rp_c")
        self.forgot("rp_c@x.com")
        tok = self.token()
        self.assertEqual(self.reset(tok), {"ok": True})
        self.assertEqual(login("rp_c", "a brand new password 42").username, "rp_c")
        with self.assertRaises(HTTPException) as ctx:
            login("rp_c", "password-for-rp_c")
        self.assertEqual(ctx.exception.status_code, 401)
        with self.assertRaises(HTTPException) as ctx:
            self.reset(tok, "another password 4242")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_every_existing_session_is_signed_out(self):
        u, token = make_user("rp_d")
        auth.current_user(req(token))  # valid before
        self.forgot("rp_d@x.com"); self.reset(self.token())
        with self.assertRaises(HTTPException):
            auth.current_user(req(token))

    def test_expired_wrong_and_short_are_refused_and_a_new_request_replaces_the_old_link(self):
        u, _ = make_user("rp_e")
        self.forgot("rp_e@x.com"); old = self.token()
        self.forgot("rp_e@x.com", ip="8.8.8.8"); new = self.token()
        for bad in (old, "x" * 43):
            with self.assertRaises(HTTPException) as ctx:
                self.reset(bad)
            self.assertEqual(ctx.exception.status_code, 400)
        with store.connect() as c:
            c.execute("UPDATE password_resets SET expires_at = datetime('now', '-1 minute') WHERE user_id = ?", (u["id"],))
        with self.assertRaises(HTTPException):
            self.reset(new)
        with self.assertRaises(ValueError):
            auth.ResetBody(token=new, password="short")

    def test_requests_are_throttled_per_email_and_attempts_per_address(self):
        for _ in range(5):
            self.forgot("spam@x.com")
        with self.assertRaises(HTTPException) as ctx:
            self.forgot("spam@x.com", ip="1.1.1.1")
        self.assertEqual(ctx.exception.status_code, 429)
        for _ in range(5):
            with self.assertRaises(HTTPException):
                self.reset("y" * 43)
        with self.assertRaises(HTTPException) as ctx:
            self.reset("y" * 43)
        self.assertEqual(ctx.exception.status_code, 429)

    def test_resetting_clears_a_login_lockout(self):
        make_user("rp_f")
        for _ in range(5):
            with self.assertRaises(HTTPException):
                login("rp_f", "wrong password here")
        self.forgot("rp_f@x.com", ip="2.2.2.2"); self.reset(self.token())
        auth._fails.pop("ip:9.9.9.9", None)
        self.assertEqual(login("rp_f", "a brand new password 42").username, "rp_f")

    def test_local_delivery_prints_the_link_to_the_terminal_only_and_never_a_password_or_email(self):
        auth.reset_delivery.deliver = self._deliver  # the real one
        make_user("rp_g")
        buf = io.StringIO()
        with contextlib.redirect_stderr(buf):
            self.forgot("rp_g@x.com")
        out = buf.getvalue()
        self.assertIn("?reset=", out); self.assertIn("rp_g", out); self.assertNotIn("rp_g@x.com", out); self.assertNotIn("password-for", out)

    def test_deleting_a_user_removes_their_reset_links(self):
        u, _ = make_user("rp_h")
        self.forgot("rp_h@x.com")
        with store.connect() as c:
            c.execute("DELETE FROM users WHERE id = ?", (u["id"],))
            self.assertEqual(c.execute("SELECT COUNT(*) FROM password_resets WHERE user_id = ?", (u["id"],)).fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
