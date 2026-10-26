"""Fetch a private calendar link safely (CLAUDE.md rule 7).

The link is a SECRET (anyone with it can read the calendar), so: https only (webcal:// is treated as
https), public addresses only (no localhost, private or link-local ranges, so it can't be used to probe the
machine or network), every redirect re-checked (max 3), 10 second timeout, 5 MB cap. Errors never include
the link. Nothing here logs the URL.
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlparse

import httpx2 as httpx

MAX_BYTES = 5_000_000
TIMEOUT = 10.0
MAX_REDIRECTS = 3


class CalendarFetchError(Exception):
    """Safe to show to the user: never contains the link."""


def normalize_link(url: str) -> str:
    url = url.strip()
    if url.lower().startswith("webcal://"):
        url = "https://" + url[len("webcal://"):]
    p = urlparse(url)
    if p.scheme != "https" or not p.hostname:
        raise CalendarFetchError("Use a secure https:// (or webcal://) calendar link.")
    if p.username or p.password:
        raise CalendarFetchError("That link isn't supported.")
    return url


def public_host(host: str) -> bool:
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        return False
    return bool(infos) and all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def host_of(url: str) -> str:
    return (urlparse(url).hostname or "")[:100]


async def fetch_calendar_text(url: str) -> str:
    current = normalize_link(url)
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=False, headers={"User-Agent": "WeekPlanner/0.1 (personal use)"}) as client:
            for _ in range(MAX_REDIRECTS + 1):
                p = urlparse(current)
                if p.scheme != "https" or not p.hostname or not public_host(p.hostname):
                    raise CalendarFetchError("That link can't be used (it must be a public https address).")
                async with client.stream("GET", current) as resp:
                    if resp.status_code in (301, 302, 303, 307, 308) and resp.headers.get("location"):
                        current = urljoin(current, resp.headers["location"])
                        continue
                    if resp.status_code in (401, 403, 404, 410):
                        raise CalendarFetchError("The calendar service refused that link. Check that it is the private iCal link and still valid.")
                    if resp.status_code >= 400:
                        raise CalendarFetchError("The calendar service returned an error. Try again later.")
                    body = b""
                    async for chunk in resp.aiter_bytes():
                        body += chunk
                        if len(body) > MAX_BYTES:
                            raise CalendarFetchError("That calendar is too large to read.")
                    return body.decode(resp.encoding or "utf-8", errors="replace")
            raise CalendarFetchError("Too many redirects.")
    except CalendarFetchError:
        raise
    except (httpx.HTTPError, UnicodeError):
        raise CalendarFetchError("Couldn't reach the calendar link (network error or timeout).")
