"""Tests for tool hook middleware, loading, and dispatch integration."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from pelmeni import tools
from pelmeni.config.models import HookConfigSchema, HooksSchema
from pelmeni.config.service import AppConfig
from pelmeni.dto.hooks import HookContext, HookResult
from pelmeni.hooks.builtins import BlocklistHook, ConfirmPromptHook, PathGuardHook
from pelmeni.hooks.chain import HookChain
from pelmeni.hooks.loader import load_hooks


def _context() -> HookContext:
    """Create a hook context shared by unit tests."""
    return HookContext(agent_role="worker", session_id="test1234")


def _tool_call(name: str, arguments: dict[str, str]) -> dict:
    """Create a function tool call using the provider wire shape."""
    return {
        "id": "call_1",
        "type": "function",
        "function": {"name": name, "arguments": json.dumps(arguments)},
    }


def test_blocklist_denies_dangerous_command() -> None:
    """BlocklistHook denies rm -rf /."""
    result = BlocklistHook()(
        _tool_call("bash", {"command": "rm -rf /"}),
        _context(),
    )

    assert result.verdict == "deny"


def test_blocklist_allows_safe_command() -> None:
    """BlocklistHook allows ls -la."""
    result = BlocklistHook()(
        _tool_call("bash", {"command": "ls -la"}),
        _context(),
    )

    assert result.verdict == "allow"


def test_path_guard_denies_outside_workspace() -> None:
    """PathGuardHook denies path=/etc/passwd."""
    result = PathGuardHook()(
        _tool_call("write", {"path": "/etc/passwd"}),
        _context(),
    )

    assert result.verdict == "deny"


def test_path_guard_allows_workspace_path() -> None:
    """PathGuardHook allows path=./src/main.py."""
    result = PathGuardHook()(
        _tool_call("write", {"path": "./src/main.py"}),
        _context(),
    )

    assert result.verdict == "allow"


def test_confirm_always_allow() -> None:
    """ConfirmPromptHook with always-allow returns allow."""
    confirm = MagicMock(return_value=False)

    result = ConfirmPromptHook(mode="always-allow", confirm_fn=confirm)(
        _tool_call("bash", {"command": "ls"}),
        _context(),
    )

    assert result.verdict == "allow"
    confirm.assert_not_called()


def test_confirm_always_deny() -> None:
    """ConfirmPromptHook with always-deny returns deny."""
    result = ConfirmPromptHook(mode="always-deny")(
        _tool_call("bash", {"command": "ls"}),
        _context(),
    )

    assert result.verdict == "deny"


def test_confirm_ask_approved() -> None:
    """ConfirmPromptHook ask mode with approval returns allow."""
    hook = ConfirmPromptHook(mode="ask", confirm_fn=lambda _: True)

    result = hook(_tool_call("bash", {"command": "ls"}), _context())

    assert result.verdict == "allow"


def test_confirm_ask_rejected() -> None:
    """ConfirmPromptHook ask mode with rejection returns deny."""
    hook = ConfirmPromptHook(mode="ask", confirm_fn=lambda _: False)

    result = hook(_tool_call("bash", {"command": "ls"}), _context())

    assert result.verdict == "deny"


def test_chain_short_circuits_on_deny() -> None:
    """First hook denies, second never called."""
    first = MagicMock(
        name="first_hook",
        return_value=HookResult(verdict="deny", reason="not allowed"),
    )
    first.name = "first"
    second = MagicMock(name="second_hook", return_value=HookResult(verdict="allow"))
    second.name = "second"
    chain = HookChain(
        [first, second],
        {"first": HookConfigSchema(), "second": HookConfigSchema()},
    )

    result = chain.run(_tool_call("bash", {"command": "ls"}), _context())

    assert result.verdict == "deny"
    second.assert_not_called()


def test_chain_modify_rewrites_tool_call() -> None:
    """Modify verdict passes rewritten tool_call to next hook."""
    original = _tool_call("bash", {"command": "unsafe"})
    rewritten = _tool_call("bash", {"command": "safe"})
    modifier = MagicMock(
        return_value=HookResult(verdict="modify", tool_call=rewritten),
    )
    modifier.name = "modifier"
    observer = MagicMock(return_value=HookResult(verdict="allow"))
    observer.name = "observer"
    chain = HookChain(
        [modifier, observer],
        {"modifier": HookConfigSchema(), "observer": HookConfigSchema()},
    )

    result = chain.run(original, _context())

    assert result.verdict == "allow"
    observer.assert_called_once_with(rewritten, _context())


def test_chain_empty_allows() -> None:
    """Empty chain returns allow."""
    result = HookChain([], {}).run(
        _tool_call("bash", {"command": "ls"}),
        _context(),
    )

    assert result.verdict == "allow"


def test_chain_hook_exception_fail_closed() -> None:
    """Hook exception with fail_open disabled denies the call."""
    failing = MagicMock(side_effect=RuntimeError("broken"))
    failing.name = "failing"
    chain = HookChain([failing], {"failing": HookConfigSchema()})

    result = chain.run(_tool_call("bash", {"command": "ls"}), _context())

    assert result.verdict == "deny"
    assert "broken" in result.reason


def test_chain_hook_exception_fail_open() -> None:
    """Hook exception with fail_open enabled continues the chain."""
    failing = MagicMock(side_effect=RuntimeError("broken"))
    failing.name = "failing"
    chain = HookChain(
        [failing],
        {"failing": HookConfigSchema(fail_open=True)},
    )

    result = chain.run(_tool_call("bash", {"command": "ls"}), _context())

    assert result.verdict == "allow"


def test_chain_tool_filter_skips_hook() -> None:
    """Hook filtered to bash is skipped for a read tool call."""
    hook = MagicMock(return_value=HookResult(verdict="deny", reason="called"))
    hook.name = "bash_only"
    chain = HookChain(
        [hook],
        {"bash_only": HookConfigSchema(tools=["bash"])},
    )

    result = chain.run(_tool_call("read", {"path": "./file.txt"}), _context())

    assert result.verdict == "allow"
    hook.assert_not_called()


def test_load_hooks_default_chain() -> None:
    """No hook config loads the three default built-ins in order."""
    config = AppConfig(models={}, agents={}, hooks=None)

    chain = load_hooks(config, {})

    assert [hook.name for hook in chain.hooks] == [
        "blocklist",
        "path_guard",
        "confirm_prompt",
    ]


def test_load_hooks_custom_order() -> None:
    """Configured built-ins load in the requested order."""
    config = AppConfig(
        models={},
        agents={},
        hooks=HooksSchema(chain=["path_guard", "blocklist"]),
    )

    chain = load_hooks(config, {})

    assert [hook.name for hook in chain.hooks] == ["path_guard", "blocklist"]


def test_load_hooks_user_module(tmp_path: Path, monkeypatch) -> None:
    """Load a hook object from a custom Python module."""
    hooks_dir = tmp_path / ".config" / "pelmeni" / "hooks"
    hooks_dir.mkdir(parents=True)
    module_path = hooks_dir / "custom.py"
    module_path.write_text(
        "from pelmeni.dto.hooks import HookResult\n"
        "class CustomHook:\n"
        "    name = 'custom'\n"
        "    def __call__(self, tool_call, context):\n"
        "        return HookResult(verdict='allow')\n"
        "hook = CustomHook()\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    config = AppConfig(
        models={},
        agents={},
        hooks=HooksSchema(chain=["custom"]),
    )

    chain = load_hooks(config, {"custom": {"module": "custom"}})

    assert [hook.name for hook in chain.hooks] == ["custom"]


def test_dispatch_passes_context_to_hooks(monkeypatch) -> None:
    """tools.dispatch invokes the hook chain with the supplied context."""
    tool_call = _tool_call("bash", {"command": "ls"})
    context = _context()
    chain = MagicMock()
    chain.run.return_value = HookResult(verdict="deny", reason="test stop")
    monkeypatch.setattr(tools, "_hook_chain", chain)

    result = tools.dispatch(tool_call, context)

    assert result == "error: blocked by hook: test stop"
    chain.run.assert_called_once_with(tool_call, context)
