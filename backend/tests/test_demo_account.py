"""The demo account is created on the first start of a fresh install only, can be switched off, and can be reset."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi import HTTPException, Request, Response

import auth
import demo_account
import store


def login(password):
    req = Request({"type": "http", "headers": [], "client": ("5.5.5.5", 1)})
    return auth.login(auth.LoginBody(username="demo", password=password), req, Response())


class DemoAccount(unittest.TestCase):
    def setUp(self):
        self._dir, self._db = store.DATA_DIR, store.DB_PATH
        self.tmp = tempfile.TemporaryDirectory()
        store.DATA_DIR, store.DB_PATH = Path(self.tmp.name), Path(self.tmp.name) / "fresh.db"
        store.init()
        auth._fails.clear()

    def tearDown(self):
        store.DATA_DIR, store.DB_PATH = self._dir, self._db
        self.tmp.cleanup()

    def test_a_brand_new_database_gets_a_working_demo_account_with_a_finished_profile(self):
        self.assertTrue(demo_account.ensure_on_first_start())
        self.assertEqual(login("jelly-demo-2026").username, "demo")
        with store.connect() as c:
            p = c.execute("SELECT complete, wake_start, wake_end, city, role FROM profiles").fetchone()
        self.assertEqual(tuple(p), (1, "07:00", "22:30", "New Haven, CT", "student"))

    def test_an_existing_installation_is_never_touched(self):
        with store.connect() as c:
            c.execute("INSERT INTO users (first_name, email, username, password_hash) VALUES ('A', 'a@x.com', 'alice', 'x')")
        self.assertFalse(demo_account.ensure_on_first_start())
        with store.connect() as c:
            self.assertEqual([r[0] for r in c.execute("SELECT username FROM users")], ["alice"])

    def test_it_can_be_switched_off_and_does_not_repeat(self):
        with mock.patch.dict(os.environ, {"DEMO_ACCOUNT": "false"}):
            self.assertFalse(demo_account.ensure_on_first_start())
        with store.connect() as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM users").fetchone()[0], 0)
        self.assertTrue(demo_account.ensure_on_first_start())
        self.assertFalse(demo_account.ensure_on_first_start())  # now there is an account, so nothing happens

    def test_reset_restores_the_password_and_profile(self):
        demo_account.ensure_on_first_start()
        with store.connect() as c:
            c.execute("UPDATE users SET password_hash = ? WHERE username = 'demo'", (auth.hasher.hash("changed-by-someone"),))
            c.execute("UPDATE profiles SET city = 'Elsewhere', complete = 0")
        self.assertEqual(demo_account.create_or_reset(), "Reset")
        self.assertEqual(login("jelly-demo-2026").username, "demo")
        with store.connect() as c:
            self.assertEqual(tuple(c.execute("SELECT city, complete FROM profiles").fetchone()), ("New Haven, CT", 1))
        with self.assertRaises(HTTPException):
            login("changed-by-someone")


if __name__ == "__main__":
    unittest.main()
