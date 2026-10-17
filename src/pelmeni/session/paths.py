"""Path computation and session directory discovery helpers."""

from __future__ import annotations

import re
import time
import uuid
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

DEFAULT_SESSIONS_ROOT = Path.home() / ".pelmeni" / "sessions"
MAIN_LOG_NAME = "main.jsonl"
SUBAGENTS_DIR_NAME = "subagents"
_SHORT_HASH_LEN = 8


def slugify_workspace(workspace: Path) -> str:
    """Derive a clean, URL/file-safe alphanumeric slug for a workspace path."""
    name = workspace.resolve().name
    if not name:
        return "root"
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", name.strip().lower())
    slug = slug.strip("-")
    return slug or "workspace"


def _generate_session_id(project_slug: str) -> str:
    timestamp_prefix = datetime.now(tz=UTC).strftime("%Y%m%dT%H%M%SZ")
    random_entropy = f"{time.time()}-{uuid.uuid4()}"
    digest = sha256(random_entropy.encode()).hexdigest()[:_SHORT_HASH_LEN]
    return f"{timestamp_prefix}_{project_slug}_{digest}"


def derive_session_path(
    workspace: Path,
    sessions_root: Path | None = None,
) -> tuple[Path, str, str]:
    """Derive the project session directory path, project slug, and session ID.

    Format: <sessions_root>/<project>/<timestamp>_<slug>_<hash>/
    """
    root = sessions_root or DEFAULT_SESSIONS_ROOT
    project_slug = slugify_workspace(workspace)
    session_id = _generate_session_id(project_slug)
    session_dir = root / project_slug / session_id
    return session_dir, project_slug, session_id


def find_latest_session(
    workspace: Path,
    sessions_root: Path | None = None,
) -> Path | None:
    """Discover the latest session directory for a workspace."""
    root = sessions_root or DEFAULT_SESSIONS_ROOT
    project_slug = slugify_workspace(workspace)
    project_dir = root / project_slug
    if not project_dir.is_dir():
        return None

    session_dirs = [
        candidate
        for candidate in project_dir.iterdir()
        if candidate.is_dir() and (candidate / MAIN_LOG_NAME).is_file()
    ]
    if not session_dirs:
        return None

    return max(session_dirs, key=lambda candidate: candidate.name)
