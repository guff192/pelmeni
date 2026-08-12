"""The agent loop. This is the heart of pelmeni — keep it small and readable.

    call LLM -> run tool calls -> append results -> repeat

No SDK, no hidden machinery: every token sent to the model is visible in
`messages` below.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import TYPE_CHECKING

from pelmeni import tools
from pelmeni.providers import router as provider

if TYPE_CHECKING:
    from pelmeni.dto.hooks import HookContext
    from pelmeni.trace import Trace


MAX_ITERATIONS = 25


def _dispatch_tool(
    messages: list[dict],
    trace: Trace,
    call: dict,
    context: HookContext,
) -> HookContext:
    tool_result = tools.dispatch(call, context)
    trace.log(
        "tool_result",
        {"tool_call_id": call["id"], "result": tool_result},
    )
    messages.append(
        {
            "role": "tool",
            "tool_call_id": call["id"],
            "content": tool_result,
        }
    )
    return replace(context, tool_history=(*context.tool_history, call))


def run(
    messages: list[dict],
    trace: Trace,
    context: HookContext,
) -> str | None:
    """Run the loop until the model answers without tool calls.

    Mutates `messages` in place (that's the point — the list IS the state).
    Returns the final assistant text, or None if the iteration cap hit.
    """
    for _ in range(MAX_ITERATIONS):
        trace.log(
            "request",
            {"messages": messages, "tools": tools.SERIALIZED_TOOLS},
        )
        try:
            resp = provider.chat(messages, tools.SERIALIZED_TOOLS)
        except provider.ProviderError as exc:
            print(f"error: LLM request failed: {exc}", file=sys.stderr)
            return None
        trace.log("response", resp)

        msg = resp["choices"][0]["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return msg.get("content") or ""

        for call in tool_calls:
            context = _dispatch_tool(messages, trace, call, context)

    print(f"error: iteration cap ({MAX_ITERATIONS}) reached", file=sys.stderr)
    return None
