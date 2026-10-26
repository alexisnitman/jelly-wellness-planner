"""Small text rules shared by agents."""

from __future__ import annotations

import re

_SAFE = re.compile(r"\b(safe|safely|safest)\b", re.I)
_CTRL = re.compile(r"[\x00-\x1f\x7f<>]")
_URLISH = re.compile(r"(https?://|www\.)\S+", re.I)


def scrub(text: str) -> str:
    """Never present food or exercise as "safe" (CLAUDE.md rule 5: no medical advice)."""
    return _SAFE.sub("suitable", text or "")


def clean_line(v: str | None, n: int) -> str:
    """One-line text for display or an .ics file: control characters (including line breaks) and angle brackets are
    removed, links are stripped (the model must not invent them), and the length is capped."""
    v = _CTRL.sub(" ", v or "")
    return re.sub(r"\s+", " ", _URLISH.sub("", v)).strip()[:n]
