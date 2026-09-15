"""Dispatching tool calls through hooks and registry handlers."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from typing import TYPE_CHECKING, Any

from pelmeni.domain import messages
from pelmeni.tools import registry as reg_module

if TYPE_CHECKING:
    from pelmeni import dto
    from pelmeni.hooks.chain import HookChain
    from pelmeni.trace import Trace
_FUNCTION_KEY = "function"
_NAME_KEY = "name"
_hook_chain: HookChain | None = None


def configure_hooks(chain: HookChain) -> None:
    """Set the hook chain used by dispatch."""
    globals()["_hook_chain"] = chain
    tools_mod = sys.modules.get("pelmeni.tools")
    if tools_mod is not None:
        setattr(tools_mod, "_hook_chain", chain)  # noqa: B010


def _run_hooks(tool_call: dict, context: dto.HookContext) -> dict | str:
    """Run configured hooks on a tool call."""
    tools_mod = sys.modules.get("pelmeni.tools")
    active_chain = _hook_chain
    if tools_mod is not None:
        active_chain = getattr(tools_mod, "_hook_chain", _hook_chain)
    if active_chain is None:
        return tool_call
    hook_result = active_chain.run(tool_call, context)
    if hook_result.verdict == "deny":
        return f"error: blocked by hook: {hook_result.reason}"
    if hook_result.verdict == "modify" and hook_result.tool_call is not None:
        return hook_result.tool_call
    return tool_call


def _parse_call_arguments(call_dict: dict) -> tuple[dict, str | None]:
    raw_args = call_dict[_FUNCTION_KEY].get("arguments") or "{}"
    try:
        return json.loads(raw_args), None
    except json.JSONDecodeError as exc:
        return {}, f"error: malformed tool arguments: {exc}"


def _execute_handler(
    spec: dto.ToolSpec | None,
    name: str,
    arguments: dict,
) -> str:
    if spec is None or spec.handler is None:
        return f"error: unknown tool '{name}'"
    try:
        outcome = spec.handler(**arguments)
    except (TypeError, ValueError) as exc:
        return f"error: invalid tool arguments: {exc}"
    if name == "bash":
        print(f"\n── bash ──\n{outcome}\n")
    return str(outcome)


def _execute_call(reg: reg_module.ToolRegistry, call_dict: dict) -> str:
    name = call_dict[_FUNCTION_KEY][_NAME_KEY]
    arguments, err = _parse_call_arguments(call_dict)
    if err is not None:
        return err
    return _execute_handler(
        reg._tools.get(name),  # noqa: SLF001
        name,
        arguments,
    )


def dispatch(
    tool_call: dict[str, Any],
    context: dto.HookContext,
    registry: reg_module.ToolRegistry | None = None,
) -> str:
    """Execute one permitted tool call from the model. Never raises."""
    reg = registry or reg_module.DEFAULT_REGISTRY
    tool_name = tool_call[_FUNCTION_KEY][_NAME_KEY]
    if not reg.is_tool_allowed(context.agent_role, tool_name):
        return (
            f"error: Tool '{tool_name}' is not permitted for role "
            f"'{context.agent_role}'."
        )
    processed_call = _run_hooks(tool_call, context)
    if isinstance(processed_call, str):
        return processed_call
    return _execute_call(reg, processed_call)


def dispatch_and_append(
    active_messages: list[messages.Message],
    trace: Trace,
    call: messages.ToolCall,
    context: dto.HookContext,
    registry: reg_module.ToolRegistry,
) -> dto.HookContext:
    """Dispatch a tool call, append ToolMessage, and update context."""
    call_dict = {
        "id": call.id,
        "type": _FUNCTION_KEY,
        _FUNCTION_KEY: {_NAME_KEY: call.name, "arguments": call.arguments},
    }
    tool_result = dispatch(call_dict, context, registry=registry)
    trace.log(
        "tool_result",
        {"tool_call_id": call.id, "result": tool_result},
    )
    active_messages.append(
        messages.ToolMessage(tool_call_id=call.id, content=tool_result),
    )
    return replace(context, tool_history=(*context.tool_history, call_dict))
