"""Tests for native tools implementation and security guards."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

from pelmeni.dto.hooks import HookContext
from pelmeni.dto.tools import AgentRole
from pelmeni.hooks.builtins import GitignoreGuardHook
from pelmeni.tools import (
    DEFAULT_REGISTRY,
    dispatch,
    edit_file,
    glob_paths,
    grep_search,
    read_path,
    write_file,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_read_path_file_with_line_numbers(tmp_path: Path) -> None:
    """Read formats file lines as 1-indexed line numbers."""
    target = tmp_path / "sample.txt"
    target.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    result = read_path(str(target))

    assert result == "1: alpha\n2: beta\n3: gamma"


def test_read_path_with_line_range(tmp_path: Path) -> None:
    """Read respects start_line and end_line parameters."""
    target = tmp_path / "sample.txt"
    target.write_text("one\ntwo\nthree\nfour\nfive\n", encoding="utf-8")

    result = read_path(str(target), start_line=2, end_line=4)

    assert result == "2: two\n3: three\n4: four"


def test_read_path_directory_listing(tmp_path: Path) -> None:
    """Read lists directory contents sorted with trailing slash for dirs."""
    (tmp_path / "sub_dir").mkdir()
    (tmp_path / "file_b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "file_a.txt").write_text("a", encoding="utf-8")

    result = read_path(str(tmp_path))

    assert result == "file_a.txt\nfile_b.txt\nsub_dir/"


def test_read_path_not_found() -> None:
    """Read returns error message for non-existent path."""
    result = read_path("/non/existent/path/file.txt")

    assert result.startswith("error:")
    assert "not found" in result.lower()


def test_read_path_large_file_elision(tmp_path: Path) -> None:
    """Read truncates very large files with an elision notice."""
    target = tmp_path / "large.txt"
    target.write_text("\n".join(f"line {idx}" for idx in range(3000)), encoding="utf-8")

    result = read_path(str(target))

    assert "1: line 0" in result
    assert "[...truncated" in result


def test_write_file_atomic_and_creates_parents(tmp_path: Path) -> None:
    """Write creates parent directories and writes content atomically."""
    target = tmp_path / "nested" / "dir" / "output.txt"

    result = write_file(str(target), "hello world")

    assert "Successfully wrote" in result
    assert target.read_text(encoding="utf-8") == "hello world"


def test_write_file_overwrites_existing(tmp_path: Path) -> None:
    """Write cleanly overwrites existing file content."""
    target = tmp_path / "existing.txt"
    target.write_text("old content", encoding="utf-8")

    result = write_file(str(target), "new content")

    assert "Successfully wrote" in result
    assert target.read_text(encoding="utf-8") == "new content"


def test_edit_file_strict_search_and_replace(tmp_path: Path) -> None:
    """Edit replaces exactly one occurrence of old_text with new_text."""
    target = tmp_path / "code.py"
    target.write_text("def foo():\n    return 1\n", encoding="utf-8")

    result = edit_file(str(target), "return 1", "return 2")

    assert "Successfully edited" in result
    assert target.read_text(encoding="utf-8") == "def foo():\n    return 2\n"


def test_edit_file_fails_when_not_found(tmp_path: Path) -> None:
    """Edit returns error when old_text does not match."""
    target = tmp_path / "code.py"
    target.write_text("def foo():\n    return 1\n", encoding="utf-8")

    result = edit_file(str(target), "return 999", "return 2")

    assert result.startswith("error:")
    assert "not found" in result.lower()
    assert target.read_text(encoding="utf-8") == "def foo():\n    return 1\n"


def test_edit_file_fails_when_multiple_matches(tmp_path: Path) -> None:
    """Edit fails fast when old_text matches multiple times."""
    target = tmp_path / "repeat.txt"
    target.write_text("item\nitem\nitem\n", encoding="utf-8")

    result = edit_file(str(target), "item", "replacement")

    assert result.startswith("error:")
    assert "matched 3 times" in result
    assert target.read_text(encoding="utf-8") == "item\nitem\nitem\n"


def test_edit_file_fails_when_missing_file() -> None:
    """Edit returns error when target file does not exist."""
    result = edit_file("/missing/file.py", "old", "new")

    assert result.startswith("error:")
    assert "not found" in result.lower()


def test_glob_paths_matching_and_exclusions(tmp_path: Path) -> None:
    """Glob finds matching files and excludes default directories."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text("print(1)", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text("assert True", encoding="utf-8")

    # Excluded directories
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "config").write_text("git", encoding="utf-8")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "lib.py").write_text("venv", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "pkg.js").write_text("js", encoding="utf-8")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "cached.pyc").write_text("cache", encoding="utf-8")

    result = glob_paths("**/*.py", path=str(tmp_path))

    assert "src/main.py" in result
    assert "tests/test_main.py" in result
    assert ".git" not in result
    assert ".venv" not in result
    assert "node_modules" not in result
    assert "__pycache__" not in result


def test_grep_search_file_and_line_anchored(tmp_path: Path) -> None:
    """Grep returns path:line:content for matching regular expressions."""
    target = tmp_path / "sample.py"
    target.write_text("import sys\n\ndef main():\n    return 42\n", encoding="utf-8")

    result = grep_search(r"def \w+\(\):", path=str(target))

    assert "3:def main():" in result


def test_grep_search_directory_recursive_with_exclusions(tmp_path: Path) -> None:
    """Grep searches directories recursively while excluding default dirs."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("TARGET = 1\n", encoding="utf-8")

    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "mod.py").write_text("TARGET = 2\n", encoding="utf-8")

    result = grep_search("TARGET", path=str(tmp_path))

    assert "pkg/mod.py:1:TARGET = 1" in result
    assert ".venv" not in result


def test_grep_search_case_insensitive(tmp_path: Path) -> None:
    """Grep respects case_sensitive flag."""
    target = tmp_path / "text.txt"
    target.write_text("Hello World\nhello world\n", encoding="utf-8")

    result = grep_search("HELLO", path=str(target), case_sensitive=False)

    assert "1:Hello World" in result
    assert "2:hello world" in result


def test_grep_search_invalid_regex() -> None:
    """Grep returns error on malformed regular expression."""
    result = grep_search("[unclosed")

    assert result.startswith("error:")
    assert "regex" in result.lower()


def test_gitignore_guard_hook_blocks_when_denied(tmp_path: Path) -> None:
    """Gitignore guard denies tool call if user rejects confirmation."""
    (tmp_path / ".gitignore").write_text(".env\nsecrets/*\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=123", encoding="utf-8")

    confirm_mock = MagicMock(return_value=False)
    hook = GitignoreGuardHook(root_dir=str(tmp_path), confirm_fn=confirm_mock)
    context = HookContext(agent_role=AgentRole.BUILDER, session_id="test")

    tool_call = {
        "function": {
            "name": "read",
            "arguments": f'{{"path": "{tmp_path / ".env"}"}}',
        },
    }

    result = hook(tool_call, context)

    assert result.verdict == "deny"
    assert "gitignore" in (result.reason or "").lower()
    confirm_mock.assert_called_once()


def test_gitignore_guard_hook_allows_when_approved(tmp_path: Path) -> None:
    """Gitignore guard allows tool call if user confirms."""
    (tmp_path / ".gitignore").write_text(".env\n", encoding="utf-8")
    (tmp_path / ".env").write_text("SECRET=123", encoding="utf-8")

    confirm_mock = MagicMock(return_value=True)
    hook = GitignoreGuardHook(root_dir=str(tmp_path), confirm_fn=confirm_mock)
    context = HookContext(agent_role=AgentRole.BUILDER, session_id="test")

    tool_call = {
        "function": {
            "name": "read",
            "arguments": f'{{"path": "{tmp_path / ".env"}"}}',
        },
    }

    result = hook(tool_call, context)

    assert result.verdict == "allow"
    confirm_mock.assert_called_once()


def test_default_registry_has_native_handlers() -> None:
    """All standard tools in DEFAULT_REGISTRY have non-None handlers."""
    for tool_name in ("read", "write", "edit", "glob", "grep"):
        spec = DEFAULT_REGISTRY._tools.get(tool_name)  # noqa: SLF001
        assert spec is not None, f"Tool {tool_name} not registered"
        assert spec.handler is not None, f"Tool {tool_name} handler is None"


def test_dispatch_executes_read_native_tool(tmp_path: Path) -> None:
    """End-to-end dispatch executes the native read tool."""
    target = tmp_path / "hello.txt"
    target.write_text("line one\nline two", encoding="utf-8")

    tool_call = {
        "function": {
            "name": "read",
            "arguments": f'{{"path": "{target}"}}',
        },
    }
    context = HookContext(agent_role=AgentRole.INVESTIGATOR, session_id="test")

    result = dispatch(tool_call, context)

    assert result == "1: line one\n2: line two"
