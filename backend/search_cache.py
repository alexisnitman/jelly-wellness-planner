"""Short-lived search results (verified classes, restaurants, movies) kept in the database instead of server memory.

Export only accepts a class, restaurant or movie that was found for THIS user and week, so those results have to survive a
server restart (otherwise approving a plan after a restart fails with "details expired"). They hold only public web
information (names, times, page links) and the user's request signature, scoped by user id; rows older than a day are
deleted. It behaves like a small dict keyed by (user_id, week_start) so the route code reads the same as before.
"""

from __future__ import annotations

import json
from datetime import date

import store


def _enc(o):
    if isinstance(o, date):
        return {"__date__": o.isoformat()}
    raise TypeError(type(o).__name__)


def _dec(d):
    return date.fromisoformat(d["__date__"]) if "__date__" in d else d


def _tuple(v):
    return tuple(_tuple(x) for x in v) if isinstance(v, list) else v


class PersistentCache:
    def __init__(self, kind: str, out_model):
        self.kind, self.out_model = kind, out_model

    def get(self, key: tuple[int, date], default=None):
        user_id, week = key
        with store.connect() as conn:
            row = conn.execute("SELECT payload FROM search_cache WHERE kind = ? AND user_id = ? AND week = ?", (self.kind, user_id, week.isoformat())).fetchone()
        if row is None:
            return default
        try:
            data = json.loads(row["payload"], object_hook=_dec)
            data["sig"] = _tuple(data["sig"])
            data["out"] = self.out_model.model_validate(data["out"])
            return data
        except Exception:
            return default  # an unreadable row is the same as no row

    def __setitem__(self, key: tuple[int, date], value: dict) -> None:
        user_id, week = key
        payload = json.dumps({**value, "out": value["out"].model_dump(mode="json")}, default=_enc)
        with store.connect() as conn:
            conn.execute("DELETE FROM search_cache WHERE saved_at < datetime('now', '-1 day')")
            conn.execute(
                "INSERT INTO search_cache (kind, user_id, week, payload) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(kind, user_id, week) DO UPDATE SET payload = excluded.payload, saved_at = datetime('now')",
                (self.kind, user_id, week.isoformat(), payload),
            )

    def pop(self, key: tuple[int, date], default=None):
        hit = self.get(key)
        with store.connect() as conn:
            conn.execute("DELETE FROM search_cache WHERE kind = ? AND user_id = ? AND week = ?", (self.kind, key[0], key[1].isoformat()))
        return default if hit is None else hit

    def clear(self) -> None:
        with store.connect() as conn:
            conn.execute("DELETE FROM search_cache WHERE kind = ?", (self.kind,))
