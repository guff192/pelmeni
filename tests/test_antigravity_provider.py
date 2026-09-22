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
            (
                '{"event":"init","conversation_id":"conv-123",'
                '"init":{"tools":["read_file","run_command","call_mcp_tool"]}}\n'
            ),
            (
                '{"event":"result","result":{"status":"SUCCESS",'
                '"response":"Hello world"}}\n'
            ),
            (
                '{"event":"init","conversation_id":"conv-123",'
                '"init":{"tools":["read_file","run_command","call_mcp_tool"]}}\n'
            ),
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
        """Wait for process completion."""
        self._running = False
        return 0


def test_factory_creates_antigravity_provider_and_fetches_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test creating Antigravity provider fetches and populates tools."""
    mock_popen = MagicMock(side_effect=MockPopen)
    monkeypatch.setattr("subprocess.Popen", mock_popen)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    AntigravityProvider.tools = []
    provider = ProviderFactory().create("antigravity")

    assert isinstance(provider, AntigravityProvider)
    assert AntigravityProvider.tools == [
        "read_file",
        "run_command",
        "call_mcp_tool",
    ]


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


def test_antigravity_session_creates_isolated_mcp_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test AntigravitySession generates isolated HOME with role-scoped MCP."""
    import json
    from pathlib import Path

    mock_popen = MagicMock(side_effect=MockPopen)
    monkeypatch.setattr("subprocess.Popen", mock_popen)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    session = AntigravitySession(
        role="investigator", session_id="test-sess-123"
    )
    session.start()

    try:
        mock_popen.assert_called_once()
        call_kwargs = mock_popen.call_args.kwargs
        env = call_kwargs.get("env")
        assert env is not None
        assert "HOME" in env
        temp_home = Path(env["HOME"])
        assert temp_home.is_dir()

        mcp_cfg_path = temp_home / ".gemini" / "config" / "mcp_config.json"
        assert mcp_cfg_path.is_file()

        data = json.loads(mcp_cfg_path.read_text(encoding="utf-8"))
        pelmeni_server = data.get("mcpServers", {}).get("pelmeni")
        assert pelmeni_server is not None
        assert "--role" in pelmeni_server["args"]
        assert "investigator" in pelmeni_server["args"]
        assert "--session-id" in pelmeni_server["args"]
        assert "test-sess-123" in pelmeni_server["args"]
    finally:
        session.close()
        assert not temp_home.exists()


def test_antigravity_provider_role_and_tool_instruction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test AntigravityProvider passes role and appends tool instructions."""
    created_popens: list[MockPopen] = []

    def mock_factory(*args: object, **kwargs: object) -> MockPopen:
        proc = MockPopen(*args, **kwargs)  # type: ignore[arg-type]
        created_popens.append(proc)
        return proc

    monkeypatch.setattr("subprocess.Popen", mock_factory)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))
    provider = AntigravityProvider(role="investigator", session_id="test-sess")
    res = provider.chat(
        messages=[{"role": "user", "content": "Search for files"}],
        tools=[{"type": "function", "function": {"name": "read"}}],
        model="antigravity:gemini-3.8-flash-low",
        credentials=NoCredentials(provider="antigravity"),
    )
    assert res["choices"][0]["message"]["content"] == "Hello world"
    assert provider.session is not None
    assert provider.session.role == "investigator"
    assert provider.session.session_id == "test-sess"

    # Verify prompt sent to agy includes the tool usage instruction
    assert len(created_popens) == 1
    send_calls = [
        call[0][0] for call in created_popens[0].stdin.write.call_args_list
    ]
    assert any("pelmeni" in call for call in send_calls)
    provider.close()


class MockMultiTurnMcpPopen:
    """Mock Popen simulating a multi-turn conversation where agy uses MCP tool."""

    def __init__(self, args: list[str], **kwargs: object) -> None:
        """Initialize mock process and setup stdout events."""
        self.args = args
        self.env = kwargs.get("env", {})
        self.stdin = MagicMock()
        self.stdout = MagicMock()
        self.stderr = MagicMock()
        self.stderr.read.return_value = ""
        self._running = True
        self.stdout.readline.side_effect = [
            # Turn 1
            '{"event":"init","conversation_id":"conv-e2e-456"}\n',
            (
                '{"event":"step_update","step_update":{"conversation_id":"conv-e2e-456",'
                '"step_index":1,"state":"DONE","step_type":"agent_response"}}\n'
            ),
            (
                '{"event":"result","result":{"status":"SUCCESS",'
                '"response":"File content read: [project] name = pelmeni"}}\n'
            ),
            # Turn 2
            (
                '{"event":"step_update","step_update":{"conversation_id":"conv-e2e-456",'
                '"step_index":2,"state":"DONE","step_type":"agent_response"}}\n'
            ),
            (
                '{"event":"result","result":{"status":"SUCCESS",'
                '"response":"Turn 2 success"}}\n'
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
        """Wait for process completion."""
        self._running = False
        return 0


def test_antigravity_provider_e2e_multi_turn_mcp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify multi-turn conversation with MCP tool routing and context persistence."""
    created_popens: list[MockMultiTurnMcpPopen] = []

    def mock_factory(*args: object, **kwargs: object) -> MockMultiTurnMcpPopen:
        proc = MockMultiTurnMcpPopen(*args, **kwargs)  # type: ignore[arg-type]
        created_popens.append(proc)
        return proc

    monkeypatch.setattr("subprocess.Popen", mock_factory)
    monkeypatch.setattr("shutil.which", MagicMock(return_value="agy"))

    provider = AntigravityProvider(
        role="investigator", session_id="session-e2e"
    )

    # Turn 1: User asks to read file, model answers
    res1 = provider.chat(
        messages=[{"role": "user", "content": "Read pyproject.toml"}],
        tools=[{"type": "function", "function": {"name": "read"}}],
        model="antigravity:gemini-3.8-flash-low",
        credentials=NoCredentials(provider="antigravity"),
    )
    assert (
        res1["choices"][0]["message"]["content"]
        == "File content read: [project] name = pelmeni"
    )
    assert provider._conversation_id == "conv-e2e-456"

    # Turn 2: Follow-up question, reusing the same persistent session
    res2 = provider.chat(
        messages=[
            {"role": "user", "content": "Read pyproject.toml"},
            {
                "role": "assistant",
                "content": "File content read: [project] name = pelmeni",
            },
            {"role": "user", "content": "What was the package name?"},
        ],
        tools=[{"type": "function", "function": {"name": "read"}}],
        model="antigravity:gemini-3.8-flash-low",
        credentials=NoCredentials(provider="antigravity"),
    )
    assert res2["choices"][0]["message"]["content"] == "Turn 2 success"
    assert provider._conversation_id == "conv-e2e-456"

    # Process was started once and kept open across turns
    assert len(created_popens) == 1
    popen = created_popens[0]
    assert popen.stdin.write.call_count == 2

    provider.close()
    assert provider.session is None
