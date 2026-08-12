"""Tests for pelmeni provider translators, HTTP handling, and router."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

import httpx
import pytest
from pydantic import SecretStr

if TYPE_CHECKING:
    from pathlib import Path
from pelmeni.auth import AuthError, AuthManager
from pelmeni.dto import ApiKeyCredentials, NoCredentials
from pelmeni.providers import ProviderError, ProviderRouter
from pelmeni.providers.anthropic import AnthropicProvider
from pelmeni.providers.google import GoogleProvider
from pelmeni.providers.google.messages import GoogleMessageTranslator
from pelmeni.providers.openai import OpenAIProvider
from pelmeni.providers.openai_compatible import OpenAICompatibleProvider


def test_resolve_credentials_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test resolving credentials from environment variable."""
    monkeypatch.setenv("PELMENI_OPENAI_API_KEY", "env-secret-key")
    creds_path = tmp_path / "credentials.toml"
    auth_mgr = AuthManager(path=creds_path, environ=None)
    cred = auth_mgr.resolve("openai")
    assert isinstance(cred, ApiKeyCredentials)
    assert cred.api_key.get_secret_value() == "env-secret-key"


def test_resolve_credentials_env_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test resolving credentials from env variable set to 'none'."""
    monkeypatch.setenv("PELMENI_OPENAI_COMPATIBLE_API_KEY", "none")
    creds_path = tmp_path / "credentials.toml"
    auth_mgr = AuthManager(path=creds_path, environ=None)
    cred = auth_mgr.resolve("openai-compatible")
    assert isinstance(cred, NoCredentials)


def test_resolve_credentials_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test resolving credentials from credentials TOML file."""
    monkeypatch.delenv("PELMENI_ANTHROPIC_API_KEY", raising=False)
    creds_path = tmp_path / "credentials.toml"
    creds_path.write_text(
        '[anthropic]\ntype = "api_key"\napi_key = "file-secret-key"\n',
        encoding="utf-8",
    )
    creds_path.chmod(0o600)
    auth_mgr = AuthManager(path=creds_path, environ=None)
    cred = auth_mgr.resolve("anthropic")
    assert isinstance(cred, ApiKeyCredentials)
    assert cred.api_key.get_secret_value() == "file-secret-key"


def test_resolve_credentials_absent_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test missing credentials raises AuthError."""
    monkeypatch.delenv("PELMENI_GOOGLE_API_KEY", raising=False)
    creds_path = tmp_path / "credentials.toml"
    auth_mgr = AuthManager(path=creds_path, environ=None)
    with pytest.raises(AuthError, match="pelmeni auth login google"):
        auth_mgr.resolve("google")


def test_router_unconfigured_chat() -> None:
    """Test calling chat on unconfigured router raises ProviderError."""
    router = ProviderRouter()
    with pytest.raises(
        ProviderError, match="Provider layer is not configured"
    ):
        router.chat([{"role": "user", "content": "hello"}])


def test_router_describe_unconfigured() -> None:
    """Test calling describe on unconfigured router raises ProviderError."""
    router = ProviderRouter()
    with pytest.raises(
        ProviderError, match="Provider layer is not configured"
    ):
        router.describe()


def test_router_configure_and_describe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test configuring router and verifying describe string."""
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        '[models]\ndefault = "openai:gpt-4o"\n\n'
        '[agents]\ndefault = { model = "default" }\n',
        encoding="utf-8",
    )
    creds_file = tmp_path / "credentials.toml"
    creds_file.write_text(
        '[openai]\ntype = "api_key"\napi_key = "key123"\n',
        encoding="utf-8",
    )
    creds_file.chmod(0o600)
    monkeypatch.delenv("PELMENI_OPENAI_API_KEY", raising=False)

    auth_mgr = AuthManager(path=creds_file, environ=None)
    router = ProviderRouter(auth_manager=auth_mgr)
    resolved = router.configure(agent="default", config_path=config_file)
    assert resolved.provider == "openai"
    assert "provider: openai" in router.describe()


def test_openai_success_text(monkeypatch: pytest.MonkeyPatch) -> None:
    """Test OpenAI success path returning text content."""
    response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Hello from OpenAI!",
                }
            }
        ]
    }
    resp = httpx.Response(
        200, content=json.dumps(response_data).encode("utf-8")
    )
    resp.request = httpx.Request(
        "POST", "https://api.openai.com/v1/chat/completions"
    )

    mock_send = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.Client.send", mock_send)

    provider = OpenAIProvider()
    creds = ApiKeyCredentials(
        provider="openai",
        api_key=SecretStr("openai-key"),
    )
    res = provider.chat(
        messages=[{"role": "user", "content": "Hi"}],
        tools=None,
        model="gpt-4o",
        credentials=creds,
    )

    assert res["choices"][0]["message"]["content"] == "Hello from OpenAI!"


def test_openai_malformed_json_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test handling malformed JSON response from OpenAI."""
    resp = httpx.Response(200, content=b"invalid json {")
    resp.request = httpx.Request(
        "POST", "https://api.openai.com/v1/chat/completions"
    )

    mock_send = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.Client.send", mock_send)

    provider = OpenAIProvider()
    creds = ApiKeyCredentials(
        provider="openai",
        api_key=SecretStr("openai-key"),
    )
    with pytest.raises(ProviderError):
        provider.chat(
            messages=[{"role": "user", "content": "Hi"}],
            tools=None,
            model="gpt-4o",
            credentials=creds,
        )


def test_openai_compatible_provider_no_auth(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test OpenAI-compatible request without authorization header."""
    response_data = {
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Local model response",
                }
            }
        ]
    }
    resp = httpx.Response(
        200, content=json.dumps(response_data).encode("utf-8")
    )
    resp.request = httpx.Request(
        "POST", "http://localhost:1234/v1/chat/completions"
    )

    mock_send = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.Client.send", mock_send)

    provider = OpenAICompatibleProvider(base_url="http://localhost:1234/v1")
    res = provider.chat(
        messages=[{"role": "user", "content": "hi"}],
        tools=None,
        model="qwen3-8b",
        credentials=NoCredentials(provider="openai-compatible"),
    )
    assert res["choices"][0]["message"]["content"] == "Local model response"
    request = mock_send.call_args[0][0]
    assert "authorization" not in request.headers
    req_body = json.loads(request.read())
    assert req_body["model"] == "qwen3-8b"


def test_openai_compatible_http_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test HTTP error status raises ProviderError."""
    resp = httpx.Response(500, content=b"Internal Error")
    resp.request = httpx.Request(
        "POST", "http://localhost:1234/v1/chat/completions"
    )

    mock_send = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.Client.send", mock_send)

    provider = OpenAICompatibleProvider(base_url="http://localhost:1234/v1")
    with pytest.raises(ProviderError):
        provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            model="qwen3-8b",
            credentials=NoCredentials(provider="openai-compatible"),
        )


def test_anthropic_multiple_tool_calls_and_json_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Anthropic multiple tool calls translation to OpenAI shape."""
    response_data = {
        "id": "msg_123",
        "type": "message",
        "role": "assistant",
        "content": [
            {
                "type": "tool_use",
                "id": "call_1",
                "name": "get_weather",
                "input": {"location": "San Francisco, CA"},
            },
            {
                "type": "tool_use",
                "id": "call_2",
                "name": "calculator",
                "input": {"expression": "2 + 2"},
            },
        ],
        "stop_reason": "tool_use",
    }
    resp = httpx.Response(
        200, content=json.dumps(response_data).encode("utf-8")
    )
    resp.request = httpx.Request(
        "POST", "https://api.anthropic.com/v1/messages"
    )

    mock_send = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.Client.send", mock_send)

    creds = ApiKeyCredentials(
        provider="anthropic",
        api_key=SecretStr("anthropic-test-key"),
    )
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "get_weather",
                "description": "Get weather",
                "parameters": {"type": "object"},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "Calculate expression",
                "parameters": {"type": "object"},
            },
        },
    ]

    monkeypatch.setattr(
        "pelmeni.providers.anthropic.AnthropicProvider._extract_api_key",
        staticmethod(lambda _credentials: "anthropic-test-key"),
    )

    provider = AnthropicProvider()
    res = provider.chat(
        messages=[
            {
                "role": "user",
                "content": "Check weather and calculate 2+2",
            }
        ],
        tools=tools,
        model="claude-3-5-sonnet-20241022",
        credentials=creds,
    )

    message = res["choices"][0]["message"]
    assert message["role"] == "assistant"
    tool_calls = message["tool_calls"]
    assert len(tool_calls) == len(tools)

    tc1 = tool_calls[0]
    assert tc1["id"] == "call_1"
    assert tc1["function"]["name"] == "get_weather"
    assert json.loads(tc1["function"]["arguments"]) == {
        "location": "San Francisco, CA"
    }

    tc2 = tool_calls[1]
    assert tc2["id"] == "call_2"
    assert tc2["function"]["name"] == "calculator"
    assert json.loads(tc2["function"]["arguments"]) == {"expression": "2 + 2"}

    request = mock_send.call_args[0][0]
    assert request.headers["x-api-key"] == "anthropic-test-key"
    assert request.headers["anthropic-version"] == "2023-06-01"


def test_anthropic_tool_result_formatting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Anthropic request tool response formatting."""
    response_data = {
        "id": "msg_124",
        "type": "message",
        "role": "assistant",
        "content": [{"type": "text", "text": "Result received"}],
    }
    resp = httpx.Response(
        200, content=json.dumps(response_data).encode("utf-8")
    )
    resp.request = httpx.Request(
        "POST", "https://api.anthropic.com/v1/messages"
    )

    mock_send = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.Client.send", mock_send)

    creds = ApiKeyCredentials(
        provider="anthropic",
        api_key=SecretStr("anthropic-key"),
    )
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "run tool"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"location":"SF"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "72 degrees",
        },
    ]

    monkeypatch.setattr(
        "pelmeni.providers.anthropic.AnthropicProvider._extract_api_key",
        staticmethod(lambda _credentials: "anthropic-key"),
    )

    provider = AnthropicProvider()
    res = provider.chat(
        messages=messages,
        tools=None,
        model="claude-3-5-sonnet",
        credentials=creds,
    )
    assert res["choices"][0]["message"]["content"] == "Result received"


def test_anthropic_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Anthropic malformed response structure raises ProviderError."""
    resp = httpx.Response(200, content=b"invalid json {")
    resp.request = httpx.Request(
        "POST", "https://api.anthropic.com/v1/messages"
    )

    mock_send = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.Client.send", mock_send)

    creds = ApiKeyCredentials(
        provider="anthropic",
        api_key=SecretStr("anthropic-key"),
    )

    monkeypatch.setattr(
        "pelmeni.providers.anthropic.AnthropicProvider._extract_api_key",
        staticmethod(lambda _credentials: "anthropic-key"),
    )

    provider = AnthropicProvider()
    with pytest.raises(ProviderError):
        provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            model="claude-3-5-sonnet",
            credentials=creds,
        )


def test_google_multiple_tool_calls_and_json_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Google Gemini multiple tool calls translation."""
    response_data = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": "fetch_url",
                                "args": {"url": "https://example.com"},
                            }
                        },
                        {
                            "functionCall": {
                                "name": "run_command",
                                "args": {"cmd": "ls -l"},
                            }
                        },
                    ],
                }
            }
        ]
    }
    resp = httpx.Response(
        200, content=json.dumps(response_data).encode("utf-8")
    )
    resp.request = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-1.5-pro:generateContent",
    )

    mock_send = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.Client.send", mock_send)

    creds = ApiKeyCredentials(
        provider="google",
        api_key=SecretStr("google-test-key"),
    )
    tools: list[dict[str, Any]] = [
        {
            "type": "function",
            "function": {
                "name": "fetch_url",
                "description": "Fetch URL",
                "parameters": {"type": "object"},
            },
        },
        {
            "type": "function",
            "function": {
                "name": "run_command",
                "description": "Run shell command",
                "parameters": {"type": "object"},
            },
        },
    ]

    monkeypatch.setattr(
        "pelmeni.providers.google.GoogleProvider._resolve_auth",
        lambda _self, _credentials: (
            {"Content-Type": "application/json"},
            {"key": "google-test-key"},
        ),
    )

    provider = GoogleProvider()
    res = provider.chat(
        messages=[{"role": "user", "content": "Fetch page and list files"}],
        tools=tools,
        model="gemini-1.5-pro",
        credentials=creds,
    )

    message = res["choices"][0]["message"]
    assert message["role"] == "assistant"
    tool_calls = message["tool_calls"]
    assert len(tool_calls) == len(tools)

    tc1 = tool_calls[0]
    assert tc1["function"]["name"] == "fetch_url"
    assert json.loads(tc1["function"]["arguments"]) == {
        "url": "https://example.com"
    }

    tc2 = tool_calls[1]
    assert tc2["function"]["name"] == "run_command"
    assert json.loads(tc2["function"]["arguments"]) == {"cmd": "ls -l"}


def test_google_tool_response_handling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Google Gemini tool result message translation."""
    response_data = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [{"text": "Done executing tools"}],
                }
            }
        ]
    }
    resp = httpx.Response(
        200, content=json.dumps(response_data).encode("utf-8")
    )
    resp.request = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-1.5-flash:generateContent",
    )

    mock_send = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.Client.send", mock_send)

    creds = ApiKeyCredentials(
        provider="google",
        api_key=SecretStr("google-key"),
    )
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": "run command"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "run_command",
                        "arguments": '{"cmd": "pwd"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "/home/user",
        },
    ]

    monkeypatch.setattr(
        "pelmeni.providers.google.GoogleProvider._resolve_auth",
        lambda _self, _credentials: (
            {"Content-Type": "application/json"},
            {"key": "google-key"},
        ),
    )

    provider = GoogleProvider()
    res = provider.chat(
        messages=messages,
        tools=None,
        model="gemini-1.5-flash",
        credentials=creds,
    )
    assert res["choices"][0]["message"]["content"] == "Done executing tools"


def test_google_malformed_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Google Gemini malformed response raises ProviderError."""
    resp = httpx.Response(200, content=b"invalid json {")
    resp.request = httpx.Request(
        "POST",
        "https://generativelanguage.googleapis.com/v1beta/models/"
        "gemini-1.5-pro:generateContent",
    )

    mock_send = MagicMock(return_value=resp)
    monkeypatch.setattr("httpx.Client.send", mock_send)

    creds = ApiKeyCredentials(
        provider="google",
        api_key=SecretStr("google-key"),
    )

    monkeypatch.setattr(
        "pelmeni.providers.google.GoogleProvider._resolve_auth",
        lambda _self, _credentials: (
            {"Content-Type": "application/json"},
            {"key": "google-key"},
        ),
    )

    provider = GoogleProvider()
    with pytest.raises(ProviderError):
        provider.chat(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            model="gemini-1.5-pro",
            credentials=creds,
        )


def test_google_translator_system_and_tool_consolidation() -> None:
    """Test system accumulation and adjacent tool consolidation."""
    translator = GoogleMessageTranslator()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": "System message 1"},
        {"role": "system", "content": "System message 2"},
        {"role": "user", "content": "User request"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "get_weather",
                        "arguments": '{"loc": "Paris"}',
                    },
                },
                {
                    "id": "c2",
                    "type": "function",
                    "function": {
                        "name": "get_time",
                        "arguments": '{"tz": "UTC"}',
                    },
                },
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "Sunny"},
        {"role": "tool", "tool_call_id": "c2", "content": "12:00"},
        {"role": "user", "content": "Follow up"},
        {"role": "tool", "tool_call_id": "c1", "content": "Rainy"},
    ]

    system_inst, contents = translator.convert_messages(messages)

    assert system_inst == {
        "parts": [{"text": "System message 1\nSystem message 2"}]
    }
    expected_total_contents = 5
    assert len(contents) == expected_total_contents

    assert contents[0]["role"] == "user"
    assert contents[0]["parts"] == [{"text": "User request"}]

    assert contents[1]["role"] == "model"
    expected_model_parts = 2
    assert len(contents[1]["parts"]) == expected_model_parts
    assert contents[1]["parts"][0]["functionCall"]["name"] == "get_weather"
    assert contents[1]["parts"][1]["functionCall"]["name"] == "get_time"

    assert contents[2]["role"] == "user"
    expected_consolidated_tool_responses = 2
    assert len(contents[2]["parts"]) == expected_consolidated_tool_responses
    assert contents[2]["parts"][0]["functionResponse"] == {
        "name": "get_weather",
        "response": {"result": "Sunny"},
    }
    assert contents[2]["parts"][1]["functionResponse"] == {
        "name": "get_time",
        "response": {"result": "12:00"},
    }

    assert contents[3]["role"] == "user"
    assert contents[3]["parts"] == [{"text": "Follow up"}]

    assert contents[4]["role"] == "user"
    assert len(contents[4]["parts"]) == 1
    assert contents[4]["parts"][0]["functionResponse"] == {
        "name": "get_weather",
        "response": {"result": "Rainy"},
    }
