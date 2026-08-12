"""CLI entry point: multi-turn REPL session with one agent or auth commands."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from pelmeni import loop, provider
from pelmeni.auth import AuthError, AuthManager
from pelmeni.config import ConfigError
from pelmeni.trace import Trace

SYSTEM_PROMPT = (
    "You are a pelmeni agent: a helpful coding assistant with a bash tool. "
    "Prefer running commands to gather facts over guessing. Be concise."
)


def _read_input() -> str | None:
    """Read one user line; None ends the session, "" skips the turn."""
    try:
        line = input("\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if line == "/exit":
        return None
    return line


def _run_repl(messages: list[dict], trace: Trace) -> None:
    """Run the REPL loop."""
    while True:
        user = _read_input()
        if user is None:
            break
        if not user:
            continue
        messages.append({"role": "user", "content": user})
        answer = loop.run(messages, trace)
        if answer:
            print(f"\n{answer}")
        else:
            print("\n(no answer; see stderr and trace)", file=sys.stderr)


def _parse_args(args: list[str]) -> argparse.Namespace:
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


def _handle_auth(parsed: argparse.Namespace) -> None:
    """Handle auth subcommand execution."""
    if parsed.auth_subcommand != "login":
        print("error: unknown auth command", file=sys.stderr)
        sys.exit(1)

    auth_manager = AuthManager()
    try:
        auth_manager.login(
            parsed.provider,
            api_key=parsed.api_key,
            client_id=parsed.client_id,
        )
    except AuthError as exc:
        print(f"error: auth failed: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"Successfully logged in for '{parsed.provider}'.")


def main() -> None:
    """Run the pelmeni REPL session or auth subcommand."""
    parsed = _parse_args(sys.argv[1:])

    if parsed.subcommand == "auth":
        _handle_auth(parsed)
        return

    try:
        provider.configure(agent="worker")
    except (ConfigError, AuthError, provider.ProviderError) as exc:
        print(f"error: configuration failed: {exc}", file=sys.stderr)
        sys.exit(1)

    trace = Trace(Path.cwd())
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"pelmeni | {provider.describe()}")
    print(f"session trace: {trace.trace_file}")
    print("type your message; Ctrl-D or /exit to quit")
    _run_repl(messages, trace)
