"""A throwaway demo account for trying the app, created automatically on the FIRST start of a fresh install.

Username `demo`, password `jelly-demo-2026` (published in the README). It is only created when the database has no accounts at all,
so it never touches an existing installation, and `DEMO_ACCOUNT=false` in the .env turns it off. This is meant for local grading and
demos: before anyone uses the app for real, turn it off and delete the demo account.
"""

from __future__ import annotations

import json
import os

import auth
import store

USERNAME, PASSWORD, EMAIL = "demo", "jelly-demo-2026", "demo@example.com"


def enabled() -> bool:
    return os.getenv("DEMO_ACCOUNT", "true").strip().lower() not in ("false", "0", "no", "off")


def create_or_reset() -> str:
    """Create the demo account (or reset its password and profile). Returns "Created" or "Reset"."""
    pw_hash = auth.hasher.hash(PASSWORD)
    with store.connect() as conn:
        row = conn.execute("SELECT id FROM users WHERE username = ?", (USERNAME,)).fetchone()
        if row is None:
            cur = conn.execute("INSERT INTO users (first_name, email, username, password_hash) VALUES (?, ?, ?, ?)", ("Demo", EMAIL, USERNAME, pw_hash))
            user_id, verb = cur.lastrowid, "Created"
        else:
            user_id, verb = row["id"], "Reset"
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (pw_hash, user_id))
        conn.execute("INSERT OR IGNORE INTO profiles (user_id) VALUES (?)", (user_id,))
        conn.execute(
            "UPDATE profiles SET wake_start='07:00', wake_end='22:30', week_start=0, timezone='America/New_York', city='New Haven, CT', diet='', limits_note='', "
            "role='student', role_details=?, complete=1, updated_at=datetime('now') WHERE user_id=?",
            (json.dumps({}), user_id),
        )
    return verb


def ensure_on_first_start() -> bool:
    """Called when the server starts. Creates the demo account only on a brand-new database. Returns True if it did."""
    if not enabled():
        return False
    with store.connect() as conn:
        if conn.execute("SELECT 1 FROM users LIMIT 1").fetchone():
            return False
    create_or_reset()
    print(f"\nDemo account created for trying the app: username '{USERNAME}', password '{PASSWORD}'\n", flush=True)
    return True
