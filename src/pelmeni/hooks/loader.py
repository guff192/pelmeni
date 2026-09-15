"""Load configured tool hook middleware."""

from __future__ import annotations

from importlib import util as importlib_util
from pathlib import Path
from typing import TYPE_CHECKING

from pelmeni.config.models import HookConfigSchema
from pelmeni.hooks.builtins import (
    BlocklistHook,
    ConfirmPromptHook,
    GitignoreGuardHook,
    PathGuardHook,
)
from pelmeni.hooks.chain import HookChain, HookError
from pelmeni.hooks.protocol import Hook

if TYPE_CHECKING:
    from importlib.machinery import ModuleSpec

    from pelmeni.config.service import AppConfig

_DEFAULT_CHAIN = ("blocklist", "path_guard", "confirm_prompt")


def _make_path_guard(config: dict) -> Hook:
    return PathGuardHook(
        allow=config.get("allow", ["./**"]),
        deny=config.get("deny", ["/etc/**", "/usr/**", "~/.ssh/**"]),
    )


def _validate_spec(name: str, config: dict) -> ModuleSpec:
    module_name = config.get("module")
    if not isinstance(module_name, str) or not module_name:
        message = f"custom hook '{name}' requires a module"
        raise HookError(message)
    config_dir = Path.home() / ".config" / "pelmeni" / "hooks"
    module_path = config_dir / f"{module_name}.py"
    spec = importlib_util.spec_from_file_location(
        f"pelmeni_user_hook_{name}",
        module_path,
    )
    if spec is None or spec.loader is None:
        message = f"cannot load hook '{name}' from '{module_path}'"
        raise HookError(message)
    return spec


def _load_user_hook(name: str, config: dict) -> Hook:
    spec = _validate_spec(name, config)
    assert spec.loader is not None  # noqa: S101
    module = importlib_util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        message = f"cannot load hook '{name}': {error}"
        raise HookError(message) from error

    hook = getattr(module, "hook", None)
    if not isinstance(hook, Hook):
        message = f"module for hook '{name}' must expose a valid 'hook'"
        raise HookError(message)
    return hook


def _make_hook(name: str, hook_config: dict) -> Hook:
    if name == "blocklist":
        return BlocklistHook()
    if name == "path_guard":
        return _make_path_guard(hook_config)
    if name == "confirm_prompt":
        return ConfirmPromptHook(mode=hook_config.get("default", "ask"))
    if name == "gitignore_guard":
        return GitignoreGuardHook(root_dir=hook_config.get("root_dir"))
    return _load_user_hook(name, hook_config)


def load_hooks(
    config: AppConfig,
    raw_hooks_config: dict[str, dict],
) -> HookChain:
    """Build the configured hook middleware chain."""
    chain_names = (
        _DEFAULT_CHAIN
        if config.hooks is None or not config.hooks.chain
        else config.hooks.chain
    )
    hooks: list[Hook] = []
    hook_configs: dict[str, HookConfigSchema] = {}
    for name in chain_names:
        hook_config = raw_hooks_config.get(name, {})
        hooks.append(_make_hook(name, hook_config))
        hook_configs[name] = HookConfigSchema.model_validate(hook_config)

    return HookChain(hooks, hook_configs)
