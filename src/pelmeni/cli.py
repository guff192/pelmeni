"""CLI entry point: multi-turn REPL session with one agent."""

import sys
from pathlib import Path

from pelmeni import loop, provider
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


def main() -> None:
    """Run the pelmeni REPL session."""
    trace = Trace(Path.cwd())
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"pelmeni | model: {provider.MODEL} @ {provider.BASE_URL}")
    print(f"session trace: {trace.trace_file}")
    print("type your message; Ctrl-D or /exit to quit")
    _run_repl(messages, trace)


if __name__ == "__main__":
    main()
