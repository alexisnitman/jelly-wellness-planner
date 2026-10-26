"""SQLite storage: accounts, sessions, password reset tokens, profiles, the (encrypted) remembered calendar link, short-lived search results, and AI usage.

Never stored: uploaded .ics files, calendar events, plans, prompts or model answers. The file lives in
backend/data/ (git-ignored, directory 0700, file 0600). Every user-data query is scoped by the user id
taken from the session, never from the request.
"""

from __future__ import annotations

import os
import sqlite3
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DATA_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DATA_DIR / "app.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  first_name    TEXT NOT NULL,
  email         TEXT NOT NULL UNIQUE,      -- stored lower-cased
  username      TEXT NOT NULL UNIQUE,      -- stored lower-cased
  password_hash TEXT NOT NULL,             -- argon2id; the password itself is never stored
  created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS sessions (
  token_hash  TEXT PRIMARY KEY,            -- sha256 of the cookie token; the raw token is never stored
  user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  created_at  TEXT NOT NULL DEFAULT (datetime('now')),
  expires_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS password_resets (
  token_hash TEXT PRIMARY KEY,             -- sha256 of the reset token; the token itself is never stored
  user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  expires_at TEXT NOT NULL,                -- 30 minutes after it was made; one use only (the row is deleted when used)
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS profiles (
  user_id     INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  wake_start  TEXT NOT NULL DEFAULT '07:00',   -- start of the user's waking hours (HH:MM)
  wake_end    TEXT NOT NULL DEFAULT '22:00',
  week_start  INTEGER NOT NULL DEFAULT 0,      -- 0 = Monday ... 6 = Sunday
  timezone    TEXT NOT NULL DEFAULT 'UTC',     -- IANA name
  city        TEXT NOT NULL DEFAULT '',
  diet        TEXT NOT NULL DEFAULT '',        -- diet and allergy notes
  limits_note TEXT NOT NULL DEFAULT '',        -- injuries or limits
  complete    INTEGER NOT NULL DEFAULT 0,      -- 1 once the user has saved the profile
  role        TEXT NOT NULL DEFAULT '',        -- 'student' | 'professional' | 'other' | ''
  role_details TEXT NOT NULL DEFAULT '{}',     -- JSON: answers to that role's follow-up questions (validated choices)
  updated_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS calendar_links (
  user_id   INTEGER PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
  url_enc   TEXT NOT NULL,                 -- Fernet-encrypted private link; never returned to the browser
  host      TEXT NOT NULL,                 -- only the host name, for display ("calendar.google.com")
  saved_at  TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS search_cache (
  kind      TEXT NOT NULL,                 -- 'class' | 'venue' | 'movie'
  user_id   INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  week      TEXT NOT NULL,                 -- first day of the planned week
  payload   TEXT NOT NULL,                 -- JSON: the verified classes, restaurants or movies found (public web information) for the user's request
  saved_at  TEXT NOT NULL DEFAULT (datetime('now')),
  PRIMARY KEY (kind, user_id, week)
);
CREATE TABLE IF NOT EXISTS ai_usage (
  id             INTEGER PRIMARY KEY AUTOINCREMENT,
  day            TEXT NOT NULL,            -- UTC date
  feature        TEXT NOT NULL,            -- feature name only
  tokens_in      INTEGER NOT NULL,
  tokens_out     INTEGER NOT NULL,
  web_searches   INTEGER NOT NULL DEFAULT 0,
  estimated_cost REAL NOT NULL
);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init() -> None:
    DATA_DIR.mkdir(mode=0o700, exist_ok=True)
    os.chmod(DATA_DIR, stat.S_IRWXU)
    with connect() as conn:
        conn.executescript(SCHEMA)
        conn.execute("DROP TABLE IF EXISTS reminders")  # the weekly reminder email feature was removed
        have = {r[1] for r in conn.execute("PRAGMA table_info(profiles)")}  # upgrade databases made before these columns existed
        for col, ddl in (("role", "TEXT NOT NULL DEFAULT ''"), ("role_details", "TEXT NOT NULL DEFAULT '{}'")):
            if col not in have:
                conn.execute(f"ALTER TABLE profiles ADD COLUMN {col} {ddl}")
    os.chmod(DB_PATH, stat.S_IRUSR | stat.S_IWUSR)


def record_usage(feature: str, tokens_in: int, tokens_out: int, web_searches: int, cost: float) -> None:
    with connect() as conn:
        conn.execute(
            "INSERT INTO ai_usage (day, feature, tokens_in, tokens_out, web_searches, estimated_cost) VALUES (date('now'), ?, ?, ?, ?, ?)",
            (feature, tokens_in, tokens_out, web_searches, cost),
        )


def spend_today() -> float:
    with connect() as conn:
        row = conn.execute("SELECT COALESCE(SUM(estimated_cost), 0) FROM ai_usage WHERE day = date('now')").fetchone()
    return float(row[0])
