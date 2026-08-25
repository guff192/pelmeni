# flake8: noqa: WPS201
"""Main CLI entry point."""

from __future__ import annotations

import argparse
import sys

from pelmeni.config.parser import ConfigError
from pelmeni.providers import router as provider

from .auth import handle_auth
from .repl import run_repl, setup_session


def parse_args(args: list[str]) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog="pelmeni",
        description="pelmeni CLI",
    )
    subparsers = parser.add_subparsers(dest="subcommand")

    auth_parser = subparsers.add_parser("auth", help="Manage authentication")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_subcommand")

    login_parser = auth_subparsers.add_parser(
        "login",
        help="Log in to provider",
    )
    login_parser.add_argument("provider", help="Provider name")
    login_parser.add_argument("--api-key", help="API key")
    login_parser.add_argument("--client-id", help="OAuth client ID")

    return parser.parse_args(args)


def main() -> None:
    """Run the pelmeni REPL session or auth subcommand."""
    parsed = parse_args(sys.argv[1:])

    if parsed.subcommand == "auth":
        handle_auth(parsed)
        return

    try:
        messages, trace, context = setup_session()
    except (ConfigError, provider.ProviderError) as exc:
        print(f"error: configuration failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"pelmeni | {provider.describe()}")
    print(f"session trace: {trace.trace_file}")
    print("type your message; Ctrl-D or /exit to quit")
    run_repl(messages, trace, context)
