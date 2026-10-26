"""How a password reset link reaches the person. LOCAL MODE: the app runs on the user's own computer and sends no email, so
the link is printed in the terminal window running the backend and the person running the app passes it on. To send real
email later, replace `deliver` (it receives the username and the link; the link carries a one-time secret, so never log it
anywhere else).
"""

from __future__ import annotations

import sys


def deliver(username: str, link: str) -> None:
    print(
        "\n=== PASSWORD RESET (local mode) ===\n"
        f"Reset link for account '{username}' (valid 30 minutes, works once):\n{link}\n"
        "===================================\n",
        file=sys.stderr,
        flush=True,
    )
