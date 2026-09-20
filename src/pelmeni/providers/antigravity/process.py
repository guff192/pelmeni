"""Execute Antigravity requests through its command-line interface."""

import shutil
import subprocess

from pelmeni.providers.base import ProviderError


def run_antigravity(
    prompt: str,
    conversation_id: str | None = None,
) -> str:
    """Run a prompt and return the raw JSON event stream.

    Args:
        prompt: Prompt supplied to the Antigravity command-line interface.
        conversation_id: Existing conversation to resume, when supplied.

    Returns:
        Standard output containing the command's event stream.

    Raises:
        ProviderError: The executable is missing or execution fails.

    """
    if shutil.which("agy") is None:
        message = "Antigravity binary 'agy' not found in PATH"
        raise ProviderError(message)

    command = [
        "agy",
        "--mode",
        "accept-edits",
        "--dangerously-skip-permissions",
        "--output-format",
        "stream-json",
        "-p",
        prompt,
    ]
    if conversation_id is not None:
        command.extend(["--conversation", conversation_id])
    completed = subprocess.run(  # noqa: S603
        command,
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        error_output = completed.stderr or completed.stdout
        message = (
            f"Antigravity process failed with code {completed.returncode}: "
            f"{error_output}"
        )
        raise ProviderError(message)
    return completed.stdout
