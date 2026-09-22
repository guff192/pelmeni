"""Execute Antigravity requests via persistent CLI sessions."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Self

from pelmeni.providers.antigravity import events
from pelmeni.providers.base import ProviderError

if TYPE_CHECKING:
    from types import TracebackType


def _build_mcp_config(role: str, session_id: str | None) -> dict:
    """Build role-scoped MCP config dictionary for pelmeni."""
    args = [
        "-m",
        "pelmeni.cli.main",
        "tools-mcp",
        "--role",
        role,
    ]
    if session_id:
        args.extend(["--session-id", session_id])
    return {
        "mcpServers": {
            "pelmeni": {
                "command": sys.executable,
                "args": args,
                "disabled": False,
            }
        }
    }


def _safe_symlink(src: Path, dest: Path) -> None:
    """Create symlink safely ignoring OSError."""
    try:
        dest.symlink_to(src)
    except OSError:
        return


def _link_gemini_assets(gemini_dir: Path) -> None:
    """Link non-config assets from user gemini directory."""
    real_gemini = Path.home() / ".gemini"
    if not real_gemini.exists():
        return
    for asset in real_gemini.iterdir():
        if asset.name != "config":
            _safe_symlink(asset, gemini_dir / asset.name)


def _setup_isolated_gemini_home(
    temp_dir: str,
    role: str,
    session_id: str | None,
) -> str:
    """Set up isolated GEMINI home directory with role-scoped MCP config."""
    gemini_dir = Path(temp_dir) / ".gemini"
    config_dir = gemini_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)

    mcp_config = _build_mcp_config(role=role, session_id=session_id)
    mcp_file = config_dir / "mcp_config.json"
    mcp_file.write_text(json.dumps(mcp_config, indent=2), encoding="utf-8")

    _link_gemini_assets(gemini_dir)
    return temp_dir


class AntigravitySession:
    """Managed persistent subprocess session for Antigravity CLI."""

    def __init__(
        self,
        model: str | None = None,
        conversation_id: str | None = None,
        role: str | None = None,
        session_id: str | None = None,
    ) -> None:
        """Initialize session parameters."""
        self.model = model
        self.conversation_id = conversation_id
        self.role = role
        self.session_id = session_id
        self.tools: list[str] = []
        self._process: subprocess.Popen[str] | None = None
        self._temp_dir: str | None = None

    def start(self) -> None:
        """Start the Antigravity background process."""
        if shutil.which("agy") is None:
            message = "Antigravity binary 'agy' not found in PATH"
            raise ProviderError(message)

        command = [
            "agy",
            "--input-format",
            "stream-json",
            "--output-format",
            "stream-json",
            "--mode",
            "accept-edits",
            "--dangerously-skip-permissions",
        ]
        if self.model:
            command.extend(["--model", self.model])
        if self.conversation_id:
            command.extend(["--conversation", self.conversation_id])

        env = dict(os.environ)
        if self.role:
            self._temp_dir = tempfile.mkdtemp(prefix="pelmeni_agy_")
            env["HOME"] = _setup_isolated_gemini_home(
                temp_dir=self._temp_dir,
                role=self.role,
                session_id=self.session_id,
            )

        try:
            self._process = subprocess.Popen(  # noqa: S603
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
        except Exception as exc:
            if self._temp_dir:
                shutil.rmtree(self._temp_dir, ignore_errors=True)
                self._temp_dir = None
            message = f"Failed to start Antigravity process: {exc}"
            raise ProviderError(message) from exc

    def is_running(self) -> bool:
        """Return True if the subprocess is currently running."""
        return bool(self._process and self._process.poll() is None)

    def send_prompt(self, prompt: str) -> str:
        """Send a prompt to stdin and read until result event.

        Args:
            prompt: User prompt to send.

        Returns:
            Assistant response text extracted from the result event.

        Raises:
            ProviderError: If process is not running, exits unexpectedly,
                or returns an error status.

        """
        if not self.is_running():
            self.start()

        if (
            self._process is None
            or self._process.stdin is None
            or self._process.stdout is None
        ):
            message = "Antigravity session pipes are not available"
            raise ProviderError(message)

        payload = {"event": "user", "message": {"content": prompt}}
        try:
            self._process.stdin.write(json.dumps(payload) + "\n")
            self._process.stdin.flush()
        except Exception as exc:
            message = f"Failed to write to session stdin: {exc}"
            raise ProviderError(message) from exc

        response_text: str | None = None
        while True:
            line = self._process.stdout.readline()
            if not line:
                self._check_process_exit()
                break

            conv_id = events.extract_init_conversation_id(line)
            if conv_id:
                self.conversation_id = conv_id
            init_tools = events.extract_init_tools(line)
            if init_tools is not None:
                self.tools = init_tools

            res = events.extract_result_response(line)
            if res is not None:
                response_text = res
                break

        if response_text is None:
            message = "Antigravity produced no result event"
            raise ProviderError(message)
        return response_text

    def _check_process_exit(self) -> None:
        """Check process exit code and raise ProviderError if failed."""
        if not self._process:
            message = "Antigravity process exited unexpectedly"
            raise ProviderError(message)
        retcode = self._process.poll()
        if retcode is not None and retcode != 0:
            stderr = self._process.stderr.read() if self._process.stderr else ""
            message = (
                f"Antigravity process failed with code {retcode}: {stderr}"
            )
            raise ProviderError(message)
        message = "Antigravity process exited unexpectedly"
        raise ProviderError(message)

    def close(self) -> None:
        """Terminate process, close pipes, and clean up temporary directory."""
        if self._process:
            try:
                if self._process.stdin:
                    self._process.stdin.close()
                if self._process.stdout:
                    self._process.stdout.close()
                if self._process.stderr:
                    self._process.stderr.close()
                if self._process.poll() is None:
                    self._process.terminate()
                    try:
                        self._process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        self._process.kill()
            finally:
                self._process = None
        if self._temp_dir:
            shutil.rmtree(self._temp_dir, ignore_errors=True)
            self._temp_dir = None

    def __enter__(self) -> Self:
        """Enter context manager."""
        self.start()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Exit context manager."""
        self.close()


def run_antigravity(
    prompt: str,
    conversation_id: str | None = None,
    model: str | None = None,
) -> str:
    """Run a prompt through an Antigravity session and return response.

    Args:
        prompt: Prompt supplied to the Antigravity command-line interface.
        conversation_id: Existing conversation to resume, when supplied.
        model: Optional model identifier.

    Returns:
        Assistant response text.

    Raises:
        ProviderError: The executable is missing or execution fails.

    """
    with AntigravitySession(
        model=model,
        conversation_id=conversation_id,
    ) as session:
        return session.send_prompt(prompt)
