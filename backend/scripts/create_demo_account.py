"""Create (or RESET) the demo account on this computer. A fresh install already creates it on the first start, so you only need this
to reset its password and profile.

    cd backend && ../.venv/bin/python scripts/create_demo_account.py

Username: demo      Password: jelly-demo-2026
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import demo_account  # noqa: E402
import store  # noqa: E402


def main() -> None:
    store.init()
    verb = demo_account.create_or_reset()
    print(f"{verb} the demo account.  Username: {demo_account.USERNAME}   Password: {demo_account.PASSWORD}")


if __name__ == "__main__":
    main()
