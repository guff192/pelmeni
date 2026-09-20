"""Contract tests for the Antigravity subscription provider."""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from pelmeni.auth import AuthManager
from pelmeni.dto import NoCredentials
from pelmeni.providers import ProviderError
from pelmeni.providers.antigravity import AntigravityProvider
from pelmeni.providers.factory import ProviderFactory

if TYPE_CHECKING:
    from pathlib import Path

_SUCCESS_OUTPUT = (
    '{"event":"init","conversation_id":"conv-123","init":{"tools":[]}}\n'
    '{"event":"step_update","step_update":{"conversation_id":"conv-123",'
    '"step_index":0,"state":"DONE","step_type":"user_input"}}\n'
    '{"event":"step_update","step_update":{"conversation_id":"conv-123",'
    '"step_index":1,"state":"ACTIVE","step_type":"agent_response",'
    '"text_delta":"Hello world"}}\n'
    '{"event":"result","result":{"conversation_id":"conv-123",'
    '"status":"SUCCESS","response":"Hello world",'
    '"usage":{"input_tokens":100,"output_tokens":10}}}\n'
)


def test_factory_creates_antigravity_provider() -> None:
    """Test creating the Antigravity provider through the factory."""
    provider = ProviderFactory().create("antigravity")

    assert isinstance(provider, AntigravityProvider)


def test_auth_resolution_antigravity(tmp_path: Path) -> None:
    """Test subscription authentication needs no API key or stored secrets."""
    auth_manager = AuthManager(
        path=tmp_path / "credentials.toml",
        environ={},
    )

    credentials = auth_manager.resolve("antigravity")

    assert isinstance(credentials, NoCredentials)
    assert credentials.provider == "antigravity"


@pytest.mark.parametrize("conversation_id", [None, "conv-123"])
def test_antigravity_provider_command_construction(
    monkeypatch: pytest.MonkeyPatch,
    conversation_id: str | None,
) -> None:
    """Test CLI flags preserve the prompt and optional conversation."""
    prompt = "Explain 'hello world'; $(do-not-execute)"
    mock_run = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=["agy"],
            returncode=0,
            stdout=_SUCCESS_OUTPUT,
            stderr="",
        ),
    )
    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    AntigravityProvider().chat(
        messages=[{"role": "user", "content": prompt}],
        tools=None,
        model="antigravity",
        credentials=NoCredentials(provider="antigravity"),
        conversation_id=conversation_id,
    )

    mock_run.assert_called_once()
    command = mock_run.call_args.args[0]
    assert command[0] == "agy"
    assert "--dangerously-skip-permissions" in command
    for flag, argument in (
        ("--mode", "accept-edits"),
        ("--output-format", "stream-json"),
        ("-p", prompt),
    ):
        assert command[command.index(flag) + 1] == argument
    if conversation_id is None:
        assert "--conversation" not in command
    else:
        assert command[command.index("--conversation") + 1] == conversation_id


def test_antigravity_provider_successful_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test NDJSON events produce one OpenAI-shaped assistant response."""
    mock_run = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=["agy"],
            returncode=0,
            stdout=_SUCCESS_OUTPUT,
            stderr="",
        ),
    )
    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    response = AntigravityProvider().chat(
        messages=[{"role": "user", "content": "Hi"}],
        tools=None,
        model="antigravity",
        credentials=NoCredentials(provider="antigravity"),
    )

    assert response["choices"] == [
        {"message": {"role": "assistant", "content": "Hello world"}},
    ]


def test_antigravity_provider_binary_not_found(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a missing executable becomes a provider error."""
    monkeypatch.setattr("shutil.which", MagicMock(return_value=None))

    with pytest.raises(ProviderError):
        AntigravityProvider().chat(
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            model="antigravity",
            credentials=NoCredentials(provider="antigravity"),
        )


def test_antigravity_provider_process_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a failed process rejects even a successful stdout result."""
    mock_run = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=["agy"],
            returncode=1,
            stdout=_SUCCESS_OUTPUT,
            stderr="Subscription authentication failed",
        ),
    )
    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    with pytest.raises(ProviderError):
        AntigravityProvider().chat(
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            model="antigravity",
            credentials=NoCredentials(provider="antigravity"),
        )


def test_antigravity_provider_error_result_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test an error result is rejected despite a successful process exit."""
    mock_run = MagicMock(
        return_value=subprocess.CompletedProcess(
            args=["agy"],
            returncode=0,
            stdout=(
                '{"event":"result","result":{"conversation_id":"conv-123",'
                '"status":"ERROR","response":"Subscription quota exceeded"}}\n'
            ),
            stderr="",
        ),
    )
    monkeypatch.setattr("subprocess.run", mock_run)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    with pytest.raises(ProviderError):
        AntigravityProvider().chat(
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            model="antigravity",
            credentials=NoCredentials(provider="antigravity"),
        )
