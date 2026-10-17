"""Encapsulated AgentSession execution module with isolated context."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pelmeni import context as ctx
from pelmeni import domain, dto, providers, tools

if TYPE_CHECKING:
    from pelmeni.context.protocol import ContextCompactor
    from pelmeni.domain.agent_profiles import AgentProfile
    from pelmeni.domain.agent_types import AgentType
    from pelmeni.hooks.chain import HookChain
    from pelmeni.session import SessionStore
    from pelmeni.tools.registry import ToolRegistry

_DEFAULT_MAX_ITERATIONS = 25


@dataclass(frozen=True)
class SessionConfig:
    """Configuration options and pluggable dependencies for an AgentSession."""

    provider: Any | None = None
    trace: SessionStore | None = None
    registry: ToolRegistry | None = None
    hook_chain: HookChain | None = None
    compaction_config: dto.CompactionConfigSchema | None = None
    compactor: ContextCompactor | None = None
    max_iterations: int = _DEFAULT_MAX_ITERATIONS


def _chat_provider(
    provider: Any,
    messages: list[dict[str, Any]],
    tool_specs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Dispatch chat request to the bound provider instance."""
    if hasattr(provider, "chat"):
        return provider.chat(
            messages=messages,
            tools=tool_specs,
        )
    error_msg = f"Provider object {provider} does not support chat"
    raise providers.ProviderError(error_msg)


def _request_turn(
    provider: Any,
    messages: list[domain.Message],
    serialized_tools: list[dict[str, Any]],
    trace: SessionStore | None,
    agent_type: str,
) -> dict[str, Any] | None:
    """Serialize messages, record trace request, and query provider."""
    serialized_messages = [domain.message_to_dto(msg) for msg in messages]
    if trace is not None:
        trace.log(
            "request",
            {
                "messages": serialized_messages,
                "tools": serialized_tools,
                "agent_type": agent_type,
            },
        )
    try:
        resp = _chat_provider(provider, serialized_messages, serialized_tools)
    except providers.ProviderError as exc:
        print(f"error: LLM request failed: {exc}", file=sys.stderr)
        return None
    if trace is not None:
        trace.log("response", resp)
    return resp


def _handle_turn_response(
    resp: dict[str, Any],
    messages: list[domain.Message],
) -> tuple[bool, str, tuple[domain.ToolCall, ...]]:
    """Parse assistant response and return termination flag and tool calls."""
    raw_msg = resp["choices"][0]["message"]
    assistant_msg = domain.message_from_dto(raw_msg)
    messages.append(assistant_msg)
    if not isinstance(assistant_msg, domain.AssistantMessage):
        return True, assistant_msg.content or "", ()
    if not assistant_msg.tool_calls:
        return True, assistant_msg.content or "", ()
    return False, "", assistant_msg.tool_calls


def _dispatch_tool_calls(
    messages: list[domain.Message],
    trace: SessionStore | None,
    tool_calls: tuple[domain.ToolCall, ...],
    exec_ctx: dto.ExecutionContext,
) -> dto.ExecutionContext:
    """Execute each tool call sequentially and return updated context."""
    active_ctx = exec_ctx
    for call in tool_calls:
        active_ctx = tools.dispatch_and_append(
            messages,
            trace,
            call,
            active_ctx,
        )
    return active_ctx


class AgentSession:
    """Manages an individual agent's lifecycle, isolated context, and turns."""

    def __init__(
        self,
        profile: AgentProfile,
        config: SessionConfig | None = None,
    ) -> None:
        """Initialize an AgentSession from profile and session config."""
        session_config = config or SessionConfig()
        self._profile = profile
        self._trace = session_config.trace
        self._compaction_config = (
            session_config.compaction_config or dto.CompactionConfigSchema()
        )
        self._compactor = (
            session_config.compactor or ctx.get_default_compactor()
        )
        self._max_iterations = session_config.max_iterations

        if session_config.provider is None:
            local_router = providers.ProviderRouter()
            local_router.configure(agent=profile.model_alias)
            self._provider = local_router
        else:
            self._provider = session_config.provider

        session_id = self._trace.session_id if self._trace else "default"
        active_registry = session_config.registry or tools.DEFAULT_REGISTRY
        hook_ctx = dto.HookContext(
            agent_role=profile.agent_type.value,
            session_id=session_id,
        )
        self._execution_context = dto.ExecutionContext(
            hook_context=hook_ctx,
            registry=active_registry,
            hook_chain=session_config.hook_chain,
        )

        self._messages: list[domain.Message] = [
            domain.SystemMessage(content=profile.system_prompt),
        ]

    @property
    def profile(self) -> AgentProfile:
        """Static AgentProfile bound to this session."""
        return self._profile

    @property
    def messages(self) -> list[domain.Message]:
        """Mutable message history for this session."""
        return self._messages

    @property
    def execution_context(self) -> dto.ExecutionContext:
        """Current execution context."""
        return self._execution_context

    def step(self, user_prompt: str | None = None) -> str:
        """Execute one conversational step or turn iteration cycle.

        Returns final assistant text response or empty string on failure.
        """
        if user_prompt is not None:
            self._messages.append(domain.UserMessage(content=user_prompt))

        serialized_tools = (
            self._execution_context.registry.get_serialized_tools(
                self._execution_context.hook_context.agent_role,
            )
        )

        for _ in range(self._max_iterations):
            is_done, answer = self._execute_turn(serialized_tools)
            if is_done:
                return answer

        print(
            f"error: iteration cap ({self._max_iterations}) reached",
            file=sys.stderr,
        )
        return ""

    def _compact_context_if_needed(self) -> None:
        """Perform isolated context compaction prior to LLM turn."""
        compact_result = self._compactor.compact(
            self._messages,
            self._compaction_config,
        )
        if compact_result.compacted:
            self._messages = list(compact_result.messages)
            if self._trace is not None:
                self._trace.log(
                    "context_compacted",
                    {
                        "original_count": compact_result.original_count,
                        "compacted_count": compact_result.compacted_count,
                        "tokens_before": compact_result.tokens_before,
                        "tokens_after": compact_result.tokens_after,
                        "agent_type": self._profile.agent_type.value,
                    },
                )

    def _execute_turn(
        self,
        serialized_tools: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """Execute a single LLM turn and tool execution phase.

        Returns a tuple of (done: bool, response_text: str).
        """
        self._compact_context_if_needed()
        resp = _request_turn(
            self._provider,
            self._messages,
            serialized_tools,
            self._trace,
            self._profile.agent_type.value,
        )
        if resp is None:
            return True, ""

        is_terminal, answer_text, tool_calls = _handle_turn_response(
            resp,
            self._messages,
        )
        if is_terminal:
            return True, answer_text

        self._execution_context = _dispatch_tool_calls(
            self._messages,
            self._trace,
            tool_calls,
            self._execution_context,
        )
        return False, ""


def create_agent_session(
    agent_type: AgentType,
    model_alias: str,
    config: SessionConfig | None = None,
) -> AgentSession:
    """Factory creating an AgentSession with standard resolved profile."""
    session_config = config or SessionConfig()
    registry = session_config.registry or tools.DEFAULT_REGISTRY
    profile = domain.get_agent_profile(
        agent_type=agent_type,
        model_alias=model_alias,
        registry=registry,
    )
    return AgentSession(profile=profile, config=session_config)
