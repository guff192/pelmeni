"""Tool registry, dispatching, and native execution handlers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pelmeni.tools.bash import execute_bash
from pelmeni.tools.dispatch import (
    configure_hooks,
    dispatch,
    dispatch_and_append,
)
from pelmeni.tools.file_ops import edit_file, read_path, write_file
from pelmeni.tools.registry import (
    BASH_TOOL,
    DEFAULT_REGISTRY,
    SERIALIZED_TOOLS,
    TOOLS,
    ToolRegistry,
)
from pelmeni.tools.search import glob_paths, grep_search
from pelmeni.tools.security import EXCLUDED_DIRS, is_gitignored

if TYPE_CHECKING:
    from pelmeni.hooks.chain import HookChain

_hook_chain: HookChain | None = None

__all__ = [
    "BASH_TOOL",
    "DEFAULT_REGISTRY",
    "EXCLUDED_DIRS",
    "SERIALIZED_TOOLS",
    "TOOLS",
    "ToolRegistry",
    "configure_hooks",
    "dispatch",
    "dispatch_and_append",
    "edit_file",
    "execute_bash",
    "glob_paths",
    "grep_search",
    "is_gitignored",
    "read_path",
    "write_file",
]
