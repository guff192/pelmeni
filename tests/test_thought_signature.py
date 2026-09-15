"""Tests for Gemini thought_signature parsing and propagation."""

from __future__ import annotations

from pelmeni.domain.message_mappers import message_from_dto, message_to_dto
from pelmeni.domain.messages import AssistantMessage, ToolCall
from pelmeni.providers.google.request import GoogleRequestTranslator
from pelmeni.providers.google.response import GoogleResponseParser


def test_domain_tool_call_thought_signature_roundtrip() -> None:
    """ToolCall preserves thought_signature through DTO conversions."""
    tool_call = ToolCall(
        id="call_1",
        name="bash",
        arguments='{"command": "ls"}',
        thought_signature="sig_test_123",
    )
    msg = AssistantMessage(content=None, tool_calls=(tool_call,))

    dto_dict = message_to_dto(msg)
    assert dto_dict["tool_calls"][0]["thought_signature"] == "sig_test_123"

    restored = message_from_dto(dto_dict)
    assert isinstance(restored, AssistantMessage)
    assert restored.tool_calls[0].thought_signature == "sig_test_123"


def test_google_response_parser_extracts_thought_signature() -> None:
    """GoogleResponseParser captures thoughtSignature from functionCall parts."""
    raw_payload = {
        "candidates": [
            {
                "content": {
                    "role": "model",
                    "parts": [
                        {
                            "functionCall": {
                                "name": "bash",
                                "args": {"command": "wc -l ./AGENTS.md"},
                            },
                            "thoughtSignature": "base64_sig_xyz",
                        },
                    ],
                },
                "finishReason": "STOP",
            },
        ],
    }
    parser = GoogleResponseParser()
    res = parser.parse_response_data(raw_payload)

    parsed_tc = res["choices"][0]["message"]["tool_calls"][0]
    assert parsed_tc["thought_signature"] == "base64_sig_xyz"


def test_google_request_translator_includes_thought_signature() -> None:
    """GoogleRequestTranslator attaches thoughtSignature to model parts."""
    messages = [
        {"role": "user", "content": "count lines"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "call_1",
                    "type": "function",
                    "function": {
                        "name": "bash",
                        "arguments": '{"command": "wc -l"}',
                    },
                    "thought_signature": "base64_sig_xyz",
                },
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "564",
        },
    ]
    translator = GoogleRequestTranslator()
    payload = translator.build_payload(messages, tools=None)

    model_part = payload["contents"][1]["parts"][0]
    assert model_part["functionCall"]["name"] == "bash"
    assert model_part["thoughtSignature"] == "base64_sig_xyz"
