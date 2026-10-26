"""Create (or reset) a throwaway demo account on THIS computer so you can try the app without filling in the sign-up form.

    cd backend && ../.venv/bin/python scripts/create_demo_account.py

Username: demo      Password: jelly-demo-2026      (the account exists only in your local database; change it any time)
The profile is already filled in (waking hours 7:00 to 22:30, New Haven CT, student), so you can go straight to planning.
Run it again to reset the demo account's password and profile.
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import auth  # noqa: E402
import store  # noqa: E402

USERNAME, PASSWORD, EMAIL = "demo", "jelly-demo-2026", "demo@example.com"


def main() -> None:
    store.init()
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
    print(f"{verb} the demo account.  Username: {USERNAME}   Password: {PASSWORD}")


if __name__ == "__main__":
    main()
