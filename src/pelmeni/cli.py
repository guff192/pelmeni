"""CLI entry point: multi-turn REPL session with one agent."""

import sys
from pathlib import Path

from . import loop, provider
from .trace import Trace

SYSTEM_PROMPT = (
    "You are a pelmeni agent: a helpful coding assistant with a bash tool. "
    "Prefer running commands to gather facts over guessing. Be concise."
)


def main() -> None:
    """Run the pelmeni REPL session."""
    trace = Trace(Path.cwd())
    messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    print(f"pelmeni | model: {provider.MODEL} @ {provider.BASE_URL}")
    print(f"session trace: {trace.trace_file}")
    print("type your message; Ctrl-D or /exit to quit")

    while True:
        try:
            user = input("\n> ").strip()
        except EOFError, KeyboardInterrupt:
            print()
            break
        if not user or user == "/exit":
            break

        messages.append({"role": "user", "content": user})
        answer = loop.run(messages, trace)
        if answer:
            print(f"\n{answer}")
        else:
            print("\n(no answer; see stderr and trace)", file=sys.stderr)


if __name__ == "__main__":
    main()
