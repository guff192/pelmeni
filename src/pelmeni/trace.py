"""JSONL session traces — our LangSmith-free observability.

Layout, pi-style:
    ~/.pelmeni/sessions/<project-name>/<session-id>/trace.jsonl

Every LLM request and response is appended as one JSON line.
"""

import json
import time
import uuid
from hashlib import sha256
from pathlib import Path

SESSIONS_ROOT = Path.home() / ".pelmeni" / "sessions"


class Trace:
    """JSONL session trace writer."""

    def __init__(self, cwd: Path):
        project = cwd.resolve().name or "root"
        session_id = sha256(
            f"{time.time()}-{uuid.uuid4()}".encode()
        ).hexdigest()[:8]
        self.dir = SESSIONS_ROOT / project / session_id
        self.dir.mkdir(parents=True, exist_ok=True)
        self.trace_file = self.dir / "trace.jsonl"

    def log(self, event: str, trace_data: dict) -> None:
        line = json.dumps(
            {"ts": time.time(), "event": event, **trace_data},
            ensure_ascii=False,
            default=str,
        )
        with self.trace_file.open("a", encoding="utf-8") as trace_file:
            trace_file.write(f"{line}\n")
