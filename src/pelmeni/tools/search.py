"""Native execution handlers for glob pattern and regex grep search."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO
from pelmeni.tools.security import EXCLUDED_DIRS, is_gitignored

_MAX_SEARCH_MATCHES = 1000


def _is_allowed_path(target_path: Path, base_root: Path) -> bool:
    """Check if target_path is allowed relative to base_root."""
    try:
        rel = target_path.relative_to(base_root)
    except ValueError:
        return False
    if any(part in EXCLUDED_DIRS for part in rel.parts):
        return False
    return not is_gitignored(target_path, root_dir=base_root)


def glob_paths(pattern: str, path: str = ".") -> str:
    """Find files matching a glob pattern, ignoring excluded directories."""
    root = Path(path)
    if not root.is_dir():
        return f"error: Directory '{path}' not found."

    discovered: list[str] = []
    try:
        discovered.extend(
            str(matched.relative_to(root))
            for matched in root.glob(pattern)
            if _is_allowed_path(matched, root)
        )
    except OSError as exc:
        return f"error: Glob failed on '{path}': {exc}"

    discovered.sort()
    if not discovered:
        return "No matching files found."
    return "\n".join(discovered)


def _match_file_lines(
    stream: TextIO,
    regex: re.Pattern,
    rel_path: str,
    matches: list[str],
) -> None:
    for line_no, line_content in enumerate(stream, start=1):
        clean_line = line_content.rstrip("\r\n")
        if regex.search(clean_line):
            matches.append(f"{rel_path}:{line_no}:{clean_line}")
            if len(matches) >= _MAX_SEARCH_MATCHES:
                return


def _search_single_file(
    file_path: Path,
    base_dir: Path,
    regex: re.Pattern,
    matches: list[str],
) -> None:
    """Search a single text file and record matching lines."""
    if file_path == base_dir:
        rel_path = file_path.name
    else:
        rel_path = str(file_path.relative_to(base_dir))
    try:
        with file_path.open(encoding="utf-8", errors="replace") as stream:
            _match_file_lines(stream, regex, rel_path, matches)
    except OSError:
        return


def _prune_excluded_dirs(dirnames: list[str]) -> None:
    for folder in list(dirnames):
        if folder in EXCLUDED_DIRS:
            dirnames.remove(folder)


def _search_directory(
    directory: Path,
    regex: re.Pattern,
    matches: list[str],
) -> None:
    """Recursively search files under a directory."""
    for root_dir, dirnames, filenames in os.walk(directory):
        _prune_excluded_dirs(dirnames)
        for filename in sorted(filenames):
            full_path = Path(root_dir) / filename
            if _is_allowed_path(full_path, directory):
                _search_single_file(full_path, directory, regex, matches)
                if len(matches) >= _MAX_SEARCH_MATCHES:
                    return


def grep_search(
    pattern: str,
    path: str = ".",
    case_sensitive: bool = True,  # noqa: FBT001, FBT002
) -> str:
    """Search files for regular expression matches anchored by line."""
    flags = 0 if case_sensitive else re.IGNORECASE
    try:
        regex = re.compile(pattern, flags=flags)
    except re.error as exc:
        return f"error: Invalid regex pattern '{pattern}': {exc}"

    target = Path(path)
    if not target.exists():
        return f"error: Path '{path}' not found."

    matches: list[str] = []
    if target.is_file():
        _search_single_file(target, target, regex, matches)
    else:
        _search_directory(target, regex, matches)

    if not matches:
        return "No matches found."
    outcome = "\n".join(matches)
    if len(matches) >= _MAX_SEARCH_MATCHES:
        outcome = f"{outcome}\n[...truncated remaining matches...]"
    return outcome
