"""Build the .ics file for an approved plan (design step 6). The file is something the user imports themselves:
the app never writes to their calendar.

Only items passed in are exported (the caller passes only approved items, after server-side re-validation).
Text is cleaned and escaped (the icalendar library escapes commas, semicolons and line breaks, and
`clean_line` removes control characters first so a title can't inject extra calendar lines).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone, tzinfo

import icalendar

from lib.analysis_text import clean_line, scrub

DISCLAIMER = "Planned with Week Planner. Workout and meal ideas are general suggestions, not medical advice."
CATEGORY = {"workout": "Workout", "cooking": "Cooking", "social": "Friends", "errand": "Errand", "rest": "Rest", "wellness": "Wellness", "other": "Plan"}


def _description(item: dict) -> str:
    lines: list[str] = []
    if item.get("why"):
        lines.append(clean_line(item["why"], 200))
    if item.get("notes"):
        lines.append(clean_line(item["notes"], 300))
    ci = item.get("class_info")
    if ci:
        lines += ["", f"CLASS: {clean_line(ci['title'], 80)} at {clean_line(ci['studio'], 80)}"]
        if ci.get("address"):
            lines.append("Address: " + clean_line(ci["address"], 120))
        if ci.get("length_assumed"):
            lines.append("The studio lists only the start time; the length shown is an assumption.")
        lines += ["Schedule source: " + ci["url"][:300], "Times can change: confirm and book on the studio's own site."]
    vi = item.get("venue_info")
    if vi:
        lines += ["", f"{(vi.get('meal') or 'dinner').upper()} OUT: {clean_line(vi['name'], 80)}" + (f" ({clean_line(vi['cuisine'], 60)})" if vi.get("cuisine") else "")]
        if vi.get("address"):
            lines.append("Address: " + clean_line(vi["address"], 120))
        walk = vi.get("style") == "walk_in"
        lines.append("Walk-in: no booking site was found for this place, so nothing was booked. It may still take bookings; opening hours and waits were not checked, so look at their page or call before you go." if walk else "A table is NOT booked by Week Planner. " + ("This time was listed on the page below when it was read; it may be gone, so book it yourself." if vi.get("availability") == "read" else "Availability was not confirmed; check it and book it yourself."))
        lines.append("Page read: " + vi["url"][:300])
        if vi.get("reservation_url"):
            lines.append("Check availability and book: " + vi["reservation_url"][:300])
        lines.append("Tell the restaurant about any allergies or diet needs; Week Planner can't tell whether any dish is safe.")
    mi = item.get("movie_info")
    if mi:
        title = clean_line(mi["title"], 100) + (f" ({mi['year']})" if mi.get("year") else "")
        lines += ["", f"MOVIE NIGHT: {title}" + (f" - {clean_line(', '.join(mi['genres']), 60)}" if mi.get("genres") else "")]
        if mi.get("where"):
            lines.append(("Showing at: " if mi.get("where_kind") == "theater" else "Where to watch: ") + clean_line(mi["where"], 60))
        elif mi.get("where_kind") != "theater":
            lines.append("Where to watch: not confirmed; check your streaming services or a rental store.")
        if mi.get("where_kind") == "theater":
            lines.append("Week Planner buys no tickets. " + ("This showtime was listed on the page below when it was read; showtimes change, so confirm and buy tickets yourself." if mi.get("availability") == "read" else "Showtimes were not confirmed; check the theater's site and buy tickets yourself."))
        lines.append("Page read: " + mi["url"][:300])
        if mi.get("watch_url"):
            lines.append(("Showtimes and tickets: " if mi.get("where_kind") == "theater" else "Watch: ") + mi["watch_url"][:300])
    r = item.get("recipe")
    if r:
        lines += ["", f"RECIPE ({r['servings']} servings, about {r['prep_minutes'] + r['cook_minutes']} min)", "Ingredients:"]
        lines += [f"- {clean_line(x, 120)}" for x in r["ingredients"]]
        lines.append("Steps:")
        lines += [f"{n}. {clean_line(x, 300)}" for n, x in enumerate(r["steps"], 1)]
    w = item.get("workout")
    if w:
        equip = f", {', '.join(clean_line(e, 60) for e in w['equipment'])}" if w["equipment"] else ""
        lines += ["", f"WORKOUT ({w['intensity']}{equip})"]
        if w.get("adaptation_note"):
            lines.append("Adapted for you: " + clean_line(w["adaptation_note"], 240))
        for label, key in (("Warm-up", "warmup"), ("Main", "main"), ("Cool-down", "cooldown")):
            if w[key]:
                lines.append(label + ":")
                lines += [f"- {clean_line(x, 200)}" for x in w[key]]
    lines += ["", DISCLAIMER]
    return scrub("\n".join(lines).strip())


def build_ics(items: list[dict], tz: tzinfo) -> bytes:
    """items: validated dicts with title, kind, day (date), start/end "HH:MM", why, notes, recipe, workout."""
    cal = icalendar.Calendar()
    cal.add("prodid", "-//Week Planner//Personal plan//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    cal.add("x-wr-calname", "Week Planner")
    stamp = datetime.now(timezone.utc)
    for it in items:
        d: date = it["day"]
        sh, sm = map(int, it["start"].split(":"))
        eh, em = map(int, it["end"].split(":"))
        ev = icalendar.Event()
        ev.add("uid", f"{uuid.uuid4()}@weekplanner.local")
        ev.add("dtstamp", stamp)
        ev.add("dtstart", datetime(d.year, d.month, d.day, sh, sm, tzinfo=tz))
        ev.add("dtend", datetime(d.year, d.month, d.day, eh, em, tzinfo=tz))
        ev.add("summary", scrub(clean_line(it["title"], 80)) or "Planned activity")
        desc = _description(it)
        if desc:
            ev.add("description", desc)
        ev.add("categories", [CATEGORY.get(it["kind"], "Plan")])
        ev.add("transp", "OPAQUE")
        cal.add_component(ev)
    cal.add_missing_timezones()  # VTIMEZONE blocks so every calendar app reads the times correctly
    return cal.to_ical()
