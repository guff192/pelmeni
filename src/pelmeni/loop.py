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
from pelmeni.context import get_default_compactor
from pelmeni.dto.context import CompactionConfigSchema
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
    """Dispatch a single tool call and append the result to messages."""
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
    compaction_config: CompactionConfigSchema | None = None,
) -> str:
    """Run the loop until the model answers without tool calls.

    Returns the final assistant text, or an empty string on failure.

    Parameters
    ----------
    messages:
        Mutable message history; modified in-place when compaction fires.
    trace:
        Session trace writer for observability.
    context:
        Optional hook context; defaults to a BUILDER agent context.
    registry:
        Optional tool registry; defaults to ``tools.DEFAULT_REGISTRY``.
    compaction_config:
        Optional compaction configuration; defaults to
        ``CompactionConfigSchema()`` when omitted.

    """
    active_registry = tools.DEFAULT_REGISTRY if registry is None else registry
    active_context = context or HookContext(
        agent_role=AgentRole.BUILDER,
        session_id="default",
    )
    serialized_tools = active_registry.get_serialized_tools(
        active_context.agent_role,
    )
    config = compaction_config or CompactionConfigSchema()
    compactor = get_default_compactor()

    for _ in range(MAX_ITERATIONS):
        # Compact context before every LLM request.
        compact_result = compactor.compact(messages, config)
        if compact_result.compacted:
            messages[:] = compact_result.messages
            trace.log(
                "context_compacted",
                {
                    "original_count": compact_result.original_count,
                    "compacted_count": compact_result.compacted_count,
                    "tokens_before": compact_result.tokens_before,
                    "tokens_after": compact_result.tokens_after,
                },
            )

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
