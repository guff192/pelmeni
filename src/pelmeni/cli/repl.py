# flake8: noqa: WPS201
"""REPL session handling."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from pelmeni import loop
from pelmeni.config import ConfigService
from pelmeni.domain.messages import SystemMessage, UserMessage
from pelmeni.dto.hooks import HookContext
from pelmeni.hooks.loader import load_hooks
from pelmeni.providers import router as provider
from pelmeni.trace import Trace

if TYPE_CHECKING:
    from pelmeni.domain.messages import Message

SYSTEM_PROMPT = (
    "You are a pelmeni agent: a helpful coding assistant with a bash tool. "
    "Prefer running commands to gather facts over guessing. Be concise."
)


def read_input() -> str | None:
    """Read one user line; None ends session, empty string skips turn."""
    try:
        line = input("\n> ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if line == "/exit":
        return None
    return line


def setup_session() -> tuple[list[Message], Trace, HookContext]:
    """Configure providers and hooks, then create session state."""
    provider.configure(agent="reviewer")
    app_config = ConfigService().load()
    loop.tools.configure_hooks(load_hooks(app_config, app_config.raw_hooks))
    trace = Trace(Path.cwd())
    return (
        [SystemMessage(content=SYSTEM_PROMPT)],
        trace,
        HookContext(agent_role="reviewer", session_id=trace.session_id),
    )


def run_repl(
    messages: list[Message],
    trace: Trace,
    context: HookContext,
) -> None:
    """Run the REPL loop."""
    while True:
        user = read_input()
        if user is None:
            break
        if not user:
            continue
        messages.append(UserMessage(content=user))
        answer = loop.run(messages, trace, context)
        if answer:
            print(f"\n{answer}")
        else:
            print("\n(no answer; see stderr and trace)", file=sys.stderr)
