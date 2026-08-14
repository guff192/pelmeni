"""The agent loop. This is the heart of pelmeni — keep it small and readable.

    call LLM -> run tool calls -> append results -> repeat

No SDK, no hidden machinery: every token sent to the model is visible in
`messages` below.
"""

from __future__ import annotations

import sys
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from pelmeni import tools
from pelmeni.dto.hooks import HookContext
from pelmeni.dto.tools import AgentRole
from pelmeni.providers import router as provider

if TYPE_CHECKING:
    from pelmeni.tools import ToolRegistry  # noqa: WPS458
    from pelmeni.trace import Trace

MAX_ITERATIONS = 25


def _dispatch_tool(
    messages: list[dict[str, Any]],
    trace: Trace,
    call: dict[str, Any],
    context: HookContext,
    registry: ToolRegistry,
) -> HookContext:
    tool_result = tools.dispatch(call, context, registry=registry)
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


def run(  # noqa: WPS210
    messages: list[dict[str, Any]],
    trace: Trace,
    context: HookContext | None = None,
    registry: ToolRegistry | None = None,
) -> str:
    """Run the loop until the model answers without tool calls.

    Returns the final assistant text, or an empty string on failure.
    """
    active_registry = tools.DEFAULT_REGISTRY if registry is None else registry
    active_context = context or HookContext(
        agent_role=AgentRole.BUILDER,
        session_id="default",
    )
    serialized_tools = active_registry.get_serialized_tools(
        active_context.agent_role,
    )
    for _ in range(MAX_ITERATIONS):
        trace.log(
            "request",
            {"messages": messages, "tools": serialized_tools},
        )
        try:
            resp = provider.chat(messages, serialized_tools)
        except provider.ProviderError as exc:
            print(f"error: LLM request failed: {exc}", file=sys.stderr)
            return ""
        trace.log("response", resp)

        msg = resp["choices"][0]["message"]
        messages.append(msg)

        tool_calls = msg.get("tool_calls")
        if not tool_calls:
            return msg.get("content") or ""

        for call in tool_calls:
            active_context = _dispatch_tool(
                messages,
                trace,
                call,
                active_context,
                active_registry,
            )

    print(f"error: iteration cap ({MAX_ITERATIONS}) reached", file=sys.stderr)
    return ""
