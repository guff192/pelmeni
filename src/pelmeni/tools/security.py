"""Security exclusions and gitignore path matching."""

from __future__ import annotations

import contextlib
import fnmatch
from pathlib import Path

EXCLUDED_DIRS = frozenset((".git", ".venv", "node_modules", "__pycache__"))
_COMMENT_CHAR = "#"
_NEGATION_CHAR = "!"
_MAX_ANCESTORS = 100


def _parse_line(raw_line: str) -> tuple[bool, str] | None:
    line = raw_line.strip()
    if not line or line.startswith(_COMMENT_CHAR):
        return None
    negated = line.startswith(_NEGATION_CHAR)
    clean = line[1:].strip() if negated else line
    return (negated, clean) if clean else None


def _parse_gitignore_patterns(gitignore_file: Path) -> list[tuple[bool, str]]:
    """Parse patterns from a .gitignore file into (negated, pattern) tuples."""
    if not gitignore_file.is_file():
        return []
    try:
        text_data = gitignore_file.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    rules: list[tuple[bool, str]] = []
    for raw_line in text_data.splitlines():
        parsed = _parse_line(raw_line)
        if parsed is not None:
            rules.append(parsed)
    return rules


def _find_gitignore_files(target: Path, root_dir: Path) -> list[Path]:
    """Find all .gitignore files from root_dir down to target directory."""
    start = target if target.is_dir() else target.parent
    resolved_root = root_dir.resolve()
    files: list[Path] = []
    for folder in (start, *start.parents):
        candidate = folder / ".gitignore"
        if candidate.is_file():
            files.append(candidate)
        if folder.resolve() == resolved_root:
            break
    files.reverse()
    return files


def _match_pattern(rel_path: str, pattern: str) -> bool:
    """Check if relative path matches a gitignore pattern."""
    clean = pattern.rstrip("/")
    if "/" in clean:
        matches_exact = fnmatch.fnmatch(rel_path, clean)
        matches_children = fnmatch.fnmatch(rel_path, f"{clean}/*")
        return matches_exact or matches_children
    parts = rel_path.split("/")
    return any(fnmatch.fnmatch(part, clean) for part in parts)


def _matches_gitignore_file(target: Path, gitignore: Path) -> bool | None:
    try:
        rel_to_base = str(target.relative_to(gitignore.parent)).replace(
            "\\",
            "/",
        )
    except ValueError:
        return None
    outcome: bool | None = None
    for negated, pattern in _parse_gitignore_patterns(gitignore):
        if _match_pattern(rel_to_base, pattern):
            outcome = not negated
    return outcome


def _is_under_excluded_dir(target: Path, resolved_root: Path) -> bool:
    with contextlib.suppress(ValueError):
        rel = target.relative_to(resolved_root)
        return any(part in EXCLUDED_DIRS for part in rel.parts)
    return False


def is_gitignored(
    path: Path | str,
    root_dir: Path | str | None = None,
) -> bool:
    """Determine if a file or directory path matches .gitignore rules."""
    target = Path(path).resolve()
    resolved_root = (
        Path.cwd().resolve() if root_dir is None else Path(root_dir).resolve()
    )
    if _is_under_excluded_dir(target, resolved_root):
        return True

    ignored = False
    for gitignore in _find_gitignore_files(target, resolved_root):
        status = _matches_gitignore_file(target, gitignore)
        if status is not None:
            ignored = status
    return ignored
