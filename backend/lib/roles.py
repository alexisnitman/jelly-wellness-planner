"""What we ask people about their situation, by role (student, working professional, other).

The profile asks "I'm a…" and then follow-up questions that depend on the answer. This module is the single source
of those questions: the API serves them to the page and validates saved answers against them (only listed choices
are accepted), and `describe_role` turns a saved profile into one line for the question agent and the planner.
"""

from __future__ import annotations

import re

# role -> list of (key, question, choices). choices == [] means a short free-text answer.
ROLE_QUESTIONS: dict[str, list[tuple[str, str, list[str]]]] = {
    "student": [
        ("level", "What are you studying?", ["High school", "Undergraduate", "Graduate or professional school", "Other"]),
        ("class_times", "When are your classes and study blocks usually?", ["Mornings", "Afternoons", "Evenings", "It varies a lot"]),
        ("load", "How heavy is your course load?", ["Light", "Moderate", "Heavy"]),
        ("living", "Where do you live?", ["On campus", "Off campus, short commute", "Off campus, long commute"]),
    ],
    "professional": [
        ("arrangement", "Where do you work?", ["In an office", "Hybrid", "Remote"]),
        ("hours", "What are your usual work hours?", ["Standard (around 9 to 5)", "Early start", "Late or flexible", "Shifts or irregular"]),
        ("meetings", "How many meetings do you usually have?", ["Few", "A moderate amount", "Back-to-back"]),
        ("commute", "How long is your commute?", ["None", "Under 30 minutes", "30 to 60 minutes", "Over an hour"]),
    ],
    "other": [
        ("typical", "What does a typical week look like for you?", []),
    ],
}
ROLES = tuple(ROLE_QUESTIONS)
_CTRL = re.compile(r"[\x00-\x1f\x7f<>]")


def clean_details(role: str, details: dict[str, str]) -> dict[str, str]:
    """Keep only answers that belong to the role's questions and are one of its choices (or short clean text)."""
    out: dict[str, str] = {}
    for key, _question, choices in ROLE_QUESTIONS.get(role, []):
        val = details.get(key)
        if not isinstance(val, str):
            continue
        val = _CTRL.sub(" ", val).strip()
        if not val:
            continue
        if choices:
            if val in choices:
                out[key] = val
        else:
            out[key] = re.sub(r"\s+", " ", val)[:200]
    return out


def describe_role(role: str, details: dict[str, str]) -> str:
    """One line for the model, or '' when the user hasn't said. Only whitelisted choices (and the short free text)."""
    if role not in ROLE_QUESTIONS:
        return ""
    label = {"student": "a student", "professional": "a working professional", "other": "something else"}[role]
    d = clean_details(role, details)
    parts = [v.lower() if role != "other" else v for v in (d.get(k) for k, _q, _c in ROLE_QUESTIONS[role]) if v]
    return label + (": " + "; ".join(parts) if parts else "")
