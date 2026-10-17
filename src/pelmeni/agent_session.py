"""Encapsulated AgentSession execution module with isolated context."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pelmeni import context as ctx
from pelmeni import domain, tools
from pelmeni.domain.agent_profiles import get_agent_profile
from pelmeni.domain.messages import SystemMessage, UserMessage
from pelmeni.dto.context import CompactionConfigSchema
from pelmeni.dto.hooks import ExecutionContext, HookContext
from pelmeni.providers import router as provider_module
from pelmeni.providers.base import ProviderError
from pelmeni.tools.dispatch import dispatch_and_append

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
    compaction_config: CompactionConfigSchema | None = None
    compactor: ContextCompactor | None = None
    max_iterations: int = _DEFAULT_MAX_ITERATIONS


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
            session_config.compaction_config or CompactionConfigSchema()
        )
        self._compactor = (
            session_config.compactor or ctx.get_default_compactor()
        )
        self._max_iterations = session_config.max_iterations

        if session_config.provider is None:
            local_router = provider_module.ProviderRouter()
            local_router.configure(agent=profile.model_alias)
            self._provider = local_router
        else:
            self._provider = session_config.provider

        session_id = self._trace.session_id if self._trace else "default"
        active_registry = session_config.registry or tools.DEFAULT_REGISTRY
        hook_ctx = HookContext(
            agent_role=profile.agent_type.value,
            session_id=session_id,
        )
        self._execution_context = ExecutionContext(
            hook_context=hook_ctx,
            registry=active_registry,
            hook_chain=session_config.hook_chain,
        )

        self._messages: list[domain.Message] = [
            SystemMessage(content=profile.system_prompt),
        ]

    @property
    def profile(self) -> AgentProfile:
        """Static AgentProfile bound to this session."""
        return self._profile

    @property
    def agent_type(self) -> AgentType:
        """AgentType of this session."""
        return self._profile.agent_type

    @property
    def messages(self) -> list[domain.Message]:
        """Mutable message history for this session."""
        return self._messages

    @property
    def execution_context(self) -> ExecutionContext:
        """Current execution context."""
        return self._execution_context

    @property
    def hook_context(self) -> HookContext:
        """Current hook execution context."""
        return self._execution_context.hook_context

    def step(self, user_prompt: str | None = None) -> str:
        """Execute one conversational step or turn iteration cycle.

        Returns final assistant text response or empty string on failure.
        """
        if user_prompt is not None:
            self._messages.append(UserMessage(content=user_prompt))

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

    def _chat_provider(
        self,
        serialized_messages: list[dict[str, Any]],
        serialized_tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Dispatch chat request to the bound provider instance."""
        if hasattr(self._provider, "chat"):
            return self._provider.chat(
                messages=serialized_messages,
                tools=serialized_tools,
            )
        error_msg = f"Provider object {self._provider} does not support chat"
        raise ProviderError(error_msg)

    def _execute_turn(
        self,
        serialized_tools: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        """Execute a single LLM turn and tool execution phase.

        Returns a tuple of (done: bool, response_text: str).
        """
        self._compact_context_if_needed()

        serialized_messages = [
            domain.message_to_dto(msg) for msg in self._messages
        ]
        if self._trace is not None:
            self._trace.log(
                "request",
                {
                    "messages": serialized_messages,
                    "tools": serialized_tools,
                    "agent_type": self._profile.agent_type.value,
                },
            )

        try:
            resp = self._chat_provider(serialized_messages, serialized_tools)
        except ProviderError as exc:
            print(f"error: LLM request failed: {exc}", file=sys.stderr)
            return True, ""

        if self._trace is not None:
            self._trace.log("response", resp)

        raw_msg = resp["choices"][0]["message"]
        assistant_msg = domain.message_from_dto(raw_msg)
        self._messages.append(assistant_msg)

        if not isinstance(assistant_msg, domain.AssistantMessage):
            return True, assistant_msg.content or ""
        if not assistant_msg.tool_calls:
            return True, assistant_msg.content or ""

        for call in assistant_msg.tool_calls:
            self._execution_context = dispatch_and_append(
                self._messages,
                self._trace,
                call,
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
    profile = get_agent_profile(
        agent_type=agent_type,
        model_alias=model_alias,
        registry=registry,
    )
    return AgentSession(profile=profile, config=session_config)
