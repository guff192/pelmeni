"""Contract tests for the Antigravity subscription provider and session."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock

import pytest

from pelmeni.auth import AuthManager
from pelmeni.dto import NoCredentials
from pelmeni.providers import ProviderError
from pelmeni.providers.antigravity import (
    AntigravityProvider,
    AntigravitySession,
)
from pelmeni.providers.factory import ProviderFactory

if TYPE_CHECKING:
    from pathlib import Path


class MockPopen:
    """Mock subprocess.Popen for testing session interaction."""

    def __init__(self, args: list[str], **_: object) -> None:
        """Initialize mock Popen."""
        self.args = args
        self.stdin = MagicMock()
        self.stdout = MagicMock()
        self.stderr = MagicMock()
        self.stderr.read.return_value = ""
        self._running = True
        self.stdout.readline.side_effect = [
            '{"event":"init","conversation_id":"conv-123"}\n',
            (
                '{"event":"result","result":{"status":"SUCCESS",'
                '"response":"Hello world"}}\n'
            ),
            '{"event":"init","conversation_id":"conv-123"}\n',
            (
                '{"event":"result","result":{"status":"SUCCESS",'
                '"response":"Hello world"}}\n'
            ),
            "",
        ]

    def poll(self) -> int | None:
        """Return process exit code."""
        return None if self._running else 0

    def terminate(self) -> None:
        """Terminate process."""
        self._running = False

    def kill(self) -> None:
        """Kill process."""
        self._running = False

    def wait(self, timeout: float | None = None) -> int:
        """Wait for process exit."""
        _ = timeout
        self._running = False
        return 0


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


def test_antigravity_session_lifecycle(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test Popen args, stdin writing, conversation ID, and result return."""
    mock_popen = MagicMock(side_effect=MockPopen)
    monkeypatch.setattr("subprocess.Popen", mock_popen)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    session = AntigravitySession(
        model="antigravity",
        conversation_id="conv-123",
    )
    response = session.send_prompt("Hello")

    assert response == "Hello world"
    assert session.conversation_id == "conv-123"
    mock_popen.assert_called_once()
    args = mock_popen.call_args.args[0]
    assert args[0] == "agy"
    assert "--input-format" in args
    assert args[args.index("--input-format") + 1] == "stream-json"
    assert "--output-format" in args
    assert args[args.index("--output-format") + 1] == "stream-json"
    assert "--conversation" in args
    assert args[args.index("--conversation") + 1] == "conv-123"
    session.close()


def test_antigravity_provider_persistent_chat(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test 2 consecutive turns reuse the same process instance."""
    mock_popen = MagicMock(side_effect=MockPopen)
    monkeypatch.setattr("subprocess.Popen", mock_popen)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    provider = AntigravityProvider()
    cred = NoCredentials(provider="antigravity")

    resp1 = provider.chat(
        messages=[{"role": "user", "content": "Hi"}],
        tools=None,
        model="antigravity",
        credentials=cred,
    )
    assert resp1["choices"][0]["message"]["content"] == "Hello world"
    assert mock_popen.call_count == 1

    resp2 = provider.chat(
        messages=[{"role": "user", "content": "How are you?"}],
        tools=None,
        model="antigravity",
        credentials=cred,
    )
    assert resp2["choices"][0]["message"]["content"] == "Hello world"
    assert mock_popen.call_count == 1
    provider.close()


def test_antigravity_session_close(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test session close terminates process and closes pipes."""
    popen_instance = MockPopen(["agy"])
    mock_popen = MagicMock(return_value=popen_instance)
    monkeypatch.setattr("subprocess.Popen", mock_popen)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    session = AntigravitySession()
    session.start()
    assert session.is_running()
    session.close()
    assert not session.is_running()
    popen_instance.stdin.close.assert_called()
    popen_instance.stdout.close.assert_called()


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


class MockDeadPopen:
    """Mock subprocess.Popen that dies unexpectedly."""

    def __init__(self, *_: object, **__: object) -> None:
        """Initialize mock dead Popen."""
        self.stdin = MagicMock()
        self.stdout = MagicMock()
        self.stderr = MagicMock()
        self.stderr.read.return_value = "Process crashed"
        self.stdout.readline.return_value = ""

    def poll(self) -> int:
        """Return non-zero exit code."""
        return 1


def test_antigravity_provider_process_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test a failed process exit raises ProviderError."""
    mock_popen = MagicMock(side_effect=MockDeadPopen)
    monkeypatch.setattr("subprocess.Popen", mock_popen)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    with pytest.raises(ProviderError):
        AntigravityProvider().chat(
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            model="antigravity",
            credentials=NoCredentials(provider="antigravity"),
        )


class MockErrorResultPopen:
    """Mock subprocess.Popen that returns ERROR result status."""

    def __init__(self, *_: object, **__: object) -> None:
        """Initialize mock error result Popen."""
        self.stdin = MagicMock()
        self.stdout = MagicMock()
        self.stderr = MagicMock()
        self.stdout.readline.side_effect = [
            (
                '{"event":"result","result":{"status":"ERROR",'
                '"response":"Quota exceeded"}}\n'
            ),
            "",
        ]

    def poll(self) -> int:
        """Return zero exit code."""
        return 0


def test_antigravity_provider_error_result_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test an error result is rejected despite a successful process exit."""
    mock_popen = MagicMock(side_effect=MockErrorResultPopen)
    monkeypatch.setattr("subprocess.Popen", mock_popen)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    with pytest.raises(ProviderError):
        AntigravityProvider().chat(
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            model="antigravity",
            credentials=NoCredentials(provider="antigravity"),
        )
