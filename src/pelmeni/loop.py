"""The agent loop. This is the heart of pelmeni — keep it small and readable.

    call LLM -> run tool calls -> append results -> repeat

No SDK, no hidden machinery: every token sent to the model is visible in
`messages` below.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

from pelmeni import context as ctx
from pelmeni import domain, dto, tools
from pelmeni.providers import router as provider

if TYPE_CHECKING:
    from pelmeni.tools import ToolRegistry  # noqa: WPS458
    from pelmeni.trace import Trace

MAX_ITERATIONS = 25


def run(  # noqa: WPS210
    messages: list[domain.Message],
    trace: Trace,
    context: dto.HookContext | None = None,
    registry: ToolRegistry | None = None,
    compaction_config: dto.CompactionConfigSchema | None = None,
) -> str:
    """Run the loop until the model answers without tool calls.

    Returns the final assistant text, or an empty string on failure.
    """
    active_registry = tools.DEFAULT_REGISTRY if registry is None else registry
    active_context = context or dto.HookContext(
        agent_role=dto.AgentRole.BUILDER,
        session_id="default",
    )
    serialized_tools = active_registry.get_serialized_tools(
        active_context.agent_role,
    )
    config = compaction_config or dto.CompactionConfigSchema()
    compactor = ctx.get_default_compactor()

    for _ in range(MAX_ITERATIONS):
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

        serialized_messages = [domain.message_to_dto(msg) for msg in messages]
        trace.log(
            "request",
            {"messages": serialized_messages, "tools": serialized_tools},
        )
        try:
            resp = provider.chat(serialized_messages, serialized_tools)
        except provider.ProviderError as exc:
            print(f"error: LLM request failed: {exc}", file=sys.stderr)
            return ""
        trace.log("response", resp)

        raw_msg = resp["choices"][0]["message"]
        assistant_msg = domain.message_from_dto(raw_msg)
        messages.append(assistant_msg)

        if not isinstance(assistant_msg, domain.AssistantMessage):
            return assistant_msg.content or ""
        if not assistant_msg.tool_calls:
            return assistant_msg.content or ""

        for call in assistant_msg.tool_calls:
            active_context = tools.dispatch_and_append(
                messages,
                trace,
                call,
                active_context,
                active_registry,
            )

    print(f"error: iteration cap ({MAX_ITERATIONS}) reached", file=sys.stderr)
    return ""
