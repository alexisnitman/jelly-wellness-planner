"""Evidence for WHY a workout, meal or habit helps a goal. Never made up.

Every health statement the app shows comes from lib/evidence/claims.json: exact quotes copied from NIH, NHS, WHO and
Harvard pages (scripts/verify_evidence.py re-checks that each quote is still on its page). The planner model may only
choose claim ids from that list; this module then decides which claims truly apply to the item (right kind of
activity, matching words in the title or recipe, ingredients actually in the recipe, a late enough dinner) and builds
what the page shows: the quote, the source name, the link and the date checked. The model's own sentence linking the
item to the user's goal is shown only if it passes a strict guard (no numbers, no medical or "proven" wording).
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

CLAIMS_PATH = Path(__file__).with_name("claims.json")
MAX_PER_ITEM = 3

# What the user can pick as "what I most want from my routine" -> the goal tags claims are filed under.
# A claim's "goals" are things its quote itself says; "related" are reasonable inferences the quote does not state (shown
# as "Related to your goal…" instead of "Linked to your goal…").
PRIORITY_TAGS: dict[str, set[str]] = {
    "More energy": {"energy"},
    "Less stress": {"stress"},
    "Better sleep": {"sleep"},
    "Consistency": {"consistency"},
    "Fitness": {"fitness"},
    "Time with people": {"connection"},
    "Focus": {"focus"},
}
PRIORITIES = tuple(PRIORITY_TAGS)

_BANNED = re.compile(r"\b(cure[sd]?|treat(s|ed|ment|ing)?|prevent(s|ed|ion)?|guarantee[sd]?|proven|prove[sd]?|clinically|diagnos\w*|heal(s|ed|ing)?|detox\w*|boost(s|ed)? your immune)\b", re.I)


@lru_cache(maxsize=1)
def _data() -> dict:
    return json.loads(CLAIMS_PATH.read_text(encoding="utf-8"))


def claims() -> list[dict]:
    return _data()["claims"]


def by_id() -> dict[str, dict]:
    return {c["id"]: c for c in claims()}


def source_name(key: str) -> str:
    return _data()["sources"].get(key, key)


def goal_tags(priorities: list[str] | None) -> set[str]:
    tags: set[str] = set()
    for p in priorities or []:
        tags |= PRIORITY_TAGS.get(p, set())
    return tags


def item_text(item: dict) -> str:
    """Everything about an item that can show what it really is (lower-case)."""
    parts = [item.get("title", ""), item.get("notes", ""), item.get("goal", "")]
    w = item.get("workout") or {}
    for k in ("equipment", "warmup", "main", "cooldown"):
        parts += w.get(k, [])
    r = item.get("recipe") or {}
    parts += r.get("ingredients", []) + r.get("steps", [])
    ci = item.get("class_info") or {}
    parts += [ci.get("title", ""), ci.get("studio", "")]
    return " ".join(str(p) for p in parts).lower()


def applies(claim: dict, item: dict) -> bool:
    """Is this claim honestly about this item?"""
    if item.get("kind") not in claim["kinds"]:
        return False
    text = item_text(item)
    if claim.get("match") and not any(k in text for k in claim["match"]):
        return False
    if claim.get("ingredients"):
        lines = " ".join((item.get("recipe") or {}).get("ingredients", [])).lower()
        hits = {w for w in claim["ingredients"] if w in lines}
        if len(hits) < claim.get("min_ingredient_hits", 1):
            return False
    if claim.get("min_end") and (item.get("end") or "00:00") < claim["min_end"]:
        return False
    return True


def candidates(kinds: set[str], priorities: list[str] | None, limit: int = 40) -> list[dict]:
    """Claims worth showing the planner: right kinds, and (when the user picked priorities) ones that serve them first."""
    tags = goal_tags(priorities)
    pool = [c for c in claims() if kinds & set(c["kinds"])]
    pool.sort(key=lambda c: (not (tags & (set(c["goals"]) | set(c.get("related", [])))) if tags else False, c["id"]))
    return pool[:limit]


def evidence_block(kinds: set[str], priorities: list[str] | None) -> str:
    lines = [f'- {c["id"]} [{"/".join(c["kinds"])}; helps: {", ".join(c["goals"])}] {c["topic"]}: "{c["quote"]}" ({source_name(c["source"])})' for c in candidates(kinds, priorities)]
    return "\n".join(lines)


def safe_goal_link(text: str | None) -> str:
    """The model's one sentence tying the item to the user's goal. Dropped unless it is plain and makes no new claims."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    if not t or len(t) > 220 or re.search(r"\d", t) or _BANNED.search(t) or re.search(r"https?://|www\.|<|>", t):
        return ""
    return t


def build_benefit(item: dict, evidence_ids: list[str] | None, goal_link: str | None, priorities: list[str] | None, checked_default: str = "") -> dict | None:
    """What the page shows under "Why this helps". None when no cited claim truly applies (then nothing is claimed)."""
    kb = by_id()
    chosen: list[dict] = []
    for cid in dict.fromkeys(evidence_ids or []):
        c = kb.get(cid)
        if c and applies(c, item) and c not in chosen:
            chosen.append(c)
    if not chosen:
        return None
    tags = goal_tags(priorities)
    chosen.sort(key=lambda c: (not (tags & set(c["goals"])), not (tags & set(c.get("related", [])))))  # claims that serve the user's goals first
    chosen = chosen[:MAX_PER_ITEM]
    stated = {t for c in chosen for t in c["goals"]}
    inferred = {t for c in chosen for t in c.get("related", [])} - stated
    direct = [p for p in (priorities or []) if PRIORITY_TAGS.get(p, set()) & stated]
    related = [p for p in (priorities or []) if p not in direct and PRIORITY_TAGS.get(p, set()) & inferred]

    def names(ps: list[str]) -> str:
        return "goal" + ("s" if len(ps) > 1 else "") + " of " + " and ".join(x.lower() for x in ps)

    if direct:
        lead = f"Linked to your {names(direct)}:"
    elif related:
        lead = f"Related to your {names(related)}:"
    else:
        lead = "Why this is good for your wellbeing:"
    matched = direct or related
    checked = _data().get("checked", checked_default)
    return {
        "lead": lead,
        "goal_link": safe_goal_link(goal_link) if matched else "",
        "evidence": [{"topic": c["topic"], "quote": c["quote"], "source": source_name(c["source"]), "url": c["url"], "checked": checked} for c in chosen],
    }
