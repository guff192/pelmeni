"""Native execution handlers for file read, write, and edit operations."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from pelmeni.tools.security import EXCLUDED_DIRS

_BINARY_CHUNK_SIZE = 8192
_MAX_DISPLAY_LINES = 2000
_NULL_BYTE = b"\x00"


def _render_lines(selected_lines: list[str], start_num: int) -> str:
    return "\n".join(
        f"{num}: {line_text}"
        for num, line_text in enumerate(selected_lines, start=start_num)
    )


def _format_lines(
    lines: list[str],
    start_line: int | None,
    end_line: int | None,
) -> str:
    """Slice and line-number a sequence of text lines."""
    total = len(lines)
    start_idx = 0 if start_line is None else max(0, start_line - 1)
    end_idx = total if end_line is None else min(total, max(0, end_line))
    if start_idx >= end_idx:
        return ""
    selected = lines[start_idx:end_idx]
    if len(selected) > _MAX_DISPLAY_LINES:
        body = _render_lines(selected[:_MAX_DISPLAY_LINES], start_idx + 1)
        return f"{body}\n[...truncated remaining lines...]"
    return _render_lines(selected, start_idx + 1)


def read_path(
    path: str,
    start_line: int | None = None,
    end_line: int | None = None,
) -> str:
    """Read a file with line numbers or list a directory."""
    target = Path(path)
    if not target.exists():
        return f"error: Path '{path}' not found."
    if target.is_dir():
        entries = sorted(
            f"{child.name}/" if child.is_dir() else child.name
            for child in target.iterdir()
            if child.name not in EXCLUDED_DIRS
        )
        return "\n".join(entries) if entries else "(empty directory)"
    try:
        raw_bytes = target.read_bytes()
    except OSError as exc:
        return f"error: Failed to read '{path}': {exc}"
    if _NULL_BYTE in raw_bytes[:_BINARY_CHUNK_SIZE]:
        return f"error: Cannot read binary file '{path}'."
    return _format_lines(
        raw_bytes.decode("utf-8", errors="replace").splitlines(),
        start_line,
        end_line,
    )


def _atomic_write(target: Path, payload: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=target.parent,
        delete=False,
    ) as temp_file:
        temp_path = temp_file.name
        temp_file.write(payload)
        temp_file.flush()
        os.fsync(temp_file.fileno())
    Path(temp_path).replace(target)


def write_file(path: str, payload: str) -> str:
    """Atomically create or overwrite a file with content."""
    target = Path(path)
    try:
        _atomic_write(target, payload)
    except OSError as exc:
        return f"error: Failed to write '{path}': {exc}"
    return f"Successfully wrote {len(payload)} characters to '{path}'."


def _edit_content(
    current_text: str,
    old_text: str,
    new_text: str,
    path: str,
) -> str:
    count = current_text.count(old_text)
    if count != 1:
        reason = "not found" if count == 0 else f"matched {count} times"
        return f"error: old_text {reason} in '{path}', must match exactly once."
    outcome = write_file(path, current_text.replace(old_text, new_text, 1))
    if outcome.startswith("error:"):
        return outcome
    return f"Successfully edited '{path}'."


def edit_file(path: str, old_text: str, new_text: str) -> str:
    """Perform a strict single-match replacement in an existing file."""
    target = Path(path)
    if not target.is_file():
        return f"error: File '{path}' not found."
    if not old_text:
        return "error: old_text cannot be empty."
    try:
        current_text = target.read_text(encoding="utf-8")
    except OSError as exc:
        return f"error: Failed to read '{path}': {exc}"
    return _edit_content(current_text, old_text, new_text, path)
