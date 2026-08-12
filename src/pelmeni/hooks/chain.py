"""Execution chain for tool call hooks."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

from pelmeni.dto.hooks import HookResult

if TYPE_CHECKING:
    from collections.abc import Sequence

    from pelmeni.config.models import HookConfigSchema
    from pelmeni.dto.hooks import HookContext
    from pelmeni.hooks.protocol import Hook

logger = logging.getLogger(__name__)


class HookError(Exception):
    """Report a failure to construct or load a hook chain."""


class HookChain:
    """Run configured hooks sequentially for each tool call."""

    def __init__(
        self,
        hooks: Sequence[Hook],
        hook_configs: dict[str, HookConfigSchema],
    ) -> None:
        self.hooks = tuple(hooks)
        self._hook_configs = hook_configs

    def run(self, tool_call: dict, context: HookContext) -> HookResult:
        """Run matching hooks until one denies the tool call."""
        current_call = tool_call
        for hook in self.hooks:
            tool_name = current_call["function"]["name"]
            if not self._should_run_hook(hook, hook.name, tool_name):
                continue
            hook_result = self._execute_hook(
                hook,
                hook.name,
                current_call,
                context,
            )
            if hook_result.verdict == "deny":
                return hook_result
            if hook_result.verdict == "modify":
                current_call = cast("dict", hook_result.tool_call)
        return HookResult(verdict="allow")

    def _should_run_hook(
        self,
        hook: Hook,  # noqa: ARG002
        name: str,
        tool_name: str,
    ) -> bool:
        config = self._hook_configs[name]
        return not config.tools or tool_name in config.tools

    def _execute_hook(
        self,
        hook: Hook,
        name: str,
        tool_call: dict,
        context: HookContext,
    ) -> HookResult:
        try:
            return hook(tool_call, context)
        except Exception as exc:  # noqa: BLE001
            if self._hook_configs[name].fail_open:
                logger.warning("Hook %r failed open: %s", name, exc)
                return HookResult(verdict="allow")
            return HookResult(
                verdict="deny",
                reason=f"hook '{name}' raised: {exc}",
            )
