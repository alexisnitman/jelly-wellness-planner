"""Download one public web page as text for an agent (CLAUDE.md rules 4 and 7: web content is untrusted data,
and fetching is restricted).

Public http(s) pages only: the host is resolved and anything private, loopback or link-local is refused (so the
model can't be steered into probing this machine or its network), every redirect is re-checked (max 3), 8 second
timeout, 400 KB read cap, text content types only. The returned text is wrapped in <untrusted_page> markers.
It also pulls out the page's links that look like a schedule, timetable, class, booking or contact page (so the
agent can follow them) and any schema.org Event / Course data embedded in the HTML.
"""

from __future__ import annotations

import ipaddress
import json
import re
import socket
from dataclasses import dataclass, field
from html import unescape
from urllib.parse import urljoin, urlparse

import httpx2 as httpx

TIMEOUT = 8.0
MAX_BYTES = 400_000
MAX_CHARS = 14_000
MAX_REDIRECTS = 3


@dataclass
class FetchState:
    """Per-run bookkeeping: how many pages may still be fetched and which URLs were really downloaded."""

    fetches_left: int = 6
    pages_read: int = 0
    fetched_urls: set[str] = field(default_factory=set)
    page_text: dict[str, str] = field(default_factory=dict)  # normalised url -> the text we actually received (for checking claims)


def norm_url(u: str) -> str:
    p = urlparse((u or "").strip())
    return f"{p.scheme.lower()}://{(p.hostname or '').lower()}{p.path.rstrip('/')}{'?' + p.query if p.query else ''}"


def public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


_HREF = re.compile(r"""(?is)<a\b[^>]*?href\s*=\s*["']([^"'#][^"']*)["'][^>]*>(.*?)</a>""")
_USEFUL = re.compile(r"(?i)schedule|timetable|calendar|classes|class-|booking|book|reserve|membership|contact|location|events|workshops")
_LD_JSON = re.compile(r"""(?is)<script[^>]+type\s*=\s*["']application/ld\+json["'][^>]*>(.*?)</script>""")


def _useful_links(html: str, base: str) -> list[str]:
    out: list[str] = []
    for href, label in _HREF.findall(html):
        label = re.sub(r"\s+", " ", unescape(re.sub(r"(?s)<[^>]+>", " ", label))).strip()[:60]
        url = urljoin(base, unescape(href.strip()))
        if urlparse(url).scheme in ("http", "https") and _USEFUL.search(url + " " + label) and url not in [o.split(": ")[-1] for o in out]:
            out.append(f"{label}: {url}" if label else url)
        if len(out) >= 20:
            break
    return out


def _walk_events(node, out: list[str], depth: int = 0) -> None:
    if depth > 10 or len(out) >= 60:
        return
    if isinstance(node, list):
        for n in node:
            _walk_events(n, out, depth + 1)
    elif isinstance(node, dict):
        kinds = node.get("@type")
        kinds = kinds if isinstance(kinds, list) else [kinds]
        if any(k in ("Event", "CourseInstance", "ExerciseAction", "SportsEvent") for k in kinds) and isinstance(node.get("name"), str):
            loc = node.get("location")
            place = loc.get("name") if isinstance(loc, dict) and isinstance(loc.get("name"), str) else ""
            out.append(f"{node['name'].strip()} | starts {node.get('startDate', '?')} | ends {node.get('endDate', '?')}" + (f" | {place}" if place else ""))
        for v in node.values():
            if isinstance(v, (list, dict)):
                _walk_events(v, out, depth + 1)


def structured_events(html: str) -> str:
    out: list[str] = []
    for block in _LD_JSON.findall(html)[:12]:
        try:
            _walk_events(json.loads(unescape(block)), out)
        except (ValueError, RecursionError):
            continue
    return ("Events in the page's structured data:\n" + "\n".join(f"- {e}" for e in out)) if out else ""


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|noscript|svg|head)\b.*?</\1>", " ", html)
    html = re.sub(r"(?i)<br\s*/?>|</(p|div|li|tr|h[1-6]|td|th)>", "\n", html)
    text = unescape(re.sub(r"(?s)<[^>]+>", " ", html))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n", text).strip()


async def fetch_page_text(url: str, state: FetchState) -> str:
    """Return the page as wrapped text, or a short message saying why it couldn't be read. Never raises."""
    if state.fetches_left <= 0:
        return "Page fetch limit reached. Report what you have."
    state.fetches_left -= 1
    original = url.strip()
    current = original
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": "JellyWellnessPlanner/0.1 (personal use)"}) as client:
            for _ in range(MAX_REDIRECTS + 1):
                p = urlparse(current)
                if p.scheme not in ("http", "https") or not p.hostname or not public_host(p.hostname):
                    return "Blocked: only public http(s) pages can be fetched."
                async with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                        current = urljoin(current, resp.headers["location"])
                        continue
                    if resp.status_code >= 400:
                        return f"Could not fetch the page (HTTP {resp.status_code})."
                    ctype = resp.headers.get("content-type", "").lower()
                    if not (ctype.startswith("text/") or "xhtml" in ctype):
                        return f"Skipped: unsupported content type ({ctype or 'unknown'}). Text pages only."
                    body = b""
                    async for chunk in resp.aiter_bytes():
                        body += chunk
                        if len(body) >= MAX_BYTES:
                            break
                    raw = body.decode(resp.encoding or "utf-8", errors="replace")
                    text = html_to_text(raw)[:MAX_CHARS]
                    extra = structured_events(raw)
                    links = _useful_links(raw, current)
                    if extra:
                        text = extra + "\n\n" + text
                    if links:
                        text += "\n\nLinks on this page that may lead to a schedule, booking or contact page:\n" + "\n".join(links)
                    state.pages_read += 1
                    state.fetched_urls.update({norm_url(original), norm_url(current)})
                    for key in {norm_url(original), norm_url(current)}:
                        state.page_text[key] = text
                    return f'<untrusted_page url="{current}">\n{text}\n</untrusted_page>'
            return "Too many redirects."
    except (httpx.HTTPError, UnicodeError):
        return "Could not fetch the page (network error or timeout)."
