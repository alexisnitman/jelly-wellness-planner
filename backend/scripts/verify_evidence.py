"""Re-download every source page in lib/evidence/claims.json and confirm each quote is still on its page.

Run from backend/ (needs internet):   ../.venv/bin/python scripts/verify_evidence.py
Exit status 1 if any quote can't be found (the page changed or moved): fix or remove that claim before shipping.
Compares text ignoring case, whitespace and curly vs straight quotes and dashes.
"""

from __future__ import annotations

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from lib.web.fetch import FetchState, fetch_page_text  # noqa: E402

CLAIMS = Path(__file__).resolve().parents[1] / "lib" / "evidence" / "claims.json"


def norm(s: str) -> str:
    s = s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("–", "-").replace("—", "-").replace(" ", " ")
    s = re.sub(r"\s+([,.;:!?)])", r"\1", re.sub(r"\s+", " ", s))  # links in the page text leave a space before punctuation
    return s.strip().lower()


async def main() -> int:
    data = json.loads(CLAIMS.read_text())
    pages: dict[str, str] = {}
    bad = 0
    for c in data["claims"]:
        url = c["url"]
        ok = False
        for attempt in range(3):  # some sites sometimes serve a shorter version of a page, so retry before reporting a miss
            if url not in pages or attempt:
                pages[url] = norm(await fetch_page_text(url, FetchState()))
            ok = norm(c["quote"]) in pages[url]
            if ok:
                break
        print(("ok     " if ok else "MISSING"), c["id"], url if not ok else "")
        bad += not ok
    print(f"\n{len(data['claims']) - bad} of {len(data['claims'])} quotes verified on their pages")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
