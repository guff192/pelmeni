# flake8: noqa: WPS201
"""Auth subcommand handling."""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from pelmeni import auth

if TYPE_CHECKING:
    import argparse


def handle_auth(parsed: argparse.Namespace) -> None:
    """Handle auth subcommand execution."""
    if parsed.auth_subcommand != "login":
        print("error: unknown auth command", file=sys.stderr)
        sys.exit(1)

    auth_manager = auth.AuthManager()
    try:
        auth_manager.login(
            parsed.provider,
            api_key=parsed.api_key,
            client_id=parsed.client_id,
        )
    except auth.AuthError as exc:
        print(f"error: auth failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Successfully logged in for '{parsed.provider}'.")
