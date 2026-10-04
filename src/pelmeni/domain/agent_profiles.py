"""Pure domain agent profile dataclass and profile loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING

from pelmeni.domain.agent_prompts import BASE_SYSTEM_PROMPTS
from pelmeni.domain.agent_types import AgentType

if TYPE_CHECKING:
    from pelmeni.tools.protocol import ToolRegistryProtocol

_READ = "read"
_WRITE = "write"
_BASH = "bash"
_GREP = "grep"
_GLOB = "glob"
_LSP = "lsp"
_EDIT = "edit"


@dataclass(frozen=True, slots=True)
class AgentProfile:
    """Static definition of an agent type."""

    agent_type: AgentType
    name: str
    system_prompt: str
    allowed_tools: tuple[str, ...]
    model_alias: str


AGENT_TOOL_WHITELISTS: MappingProxyType[
    AgentType,
    tuple[str, ...],
] = MappingProxyType(
    {
        AgentType.MANAGER: (_READ,),
        AgentType.INVESTIGATOR: (_GREP, _GLOB, _LSP, _READ),
        AgentType.BUILDER: (_READ, _EDIT, _WRITE, _BASH),
        AgentType.REVIEWER: (_READ, _GREP, _LSP, _BASH),
        AgentType.TESTER: (_BASH, _WRITE, _READ),
    },
)


def load_agent_prompt(
    agent_type: AgentType,
    config_dir: Path | None = None,
) -> str:
    """Load system prompt for an agent type, checking user overrides first.

    Overrides are read from ~/.config/pelmeni/agents/<agent_type>.md if present.
    """
    base_dir = Path.home() / ".config" / "pelmeni" / "agents"
    target_dir = config_dir or base_dir
    override_file = target_dir / f"{agent_type.value}.md"
    if override_file.is_file():
        return override_file.read_text(encoding="utf-8")
    return BASE_SYSTEM_PROMPTS[agent_type]


def get_agent_profile(
    agent_type: AgentType,
    model_alias: str,
    name: str | None = None,
    config_dir: Path | None = None,
    registry: ToolRegistryProtocol | None = None,
) -> AgentProfile:
    """Construct an AgentProfile and validate tools against the registry."""
    prompt = load_agent_prompt(agent_type, config_dir=config_dir)
    allowed_tools = AGENT_TOOL_WHITELISTS[agent_type]

    if registry is not None:
        for tool_name in allowed_tools:
            if not registry.is_tool_allowed(agent_type.value, tool_name):
                error_message = (
                    f"Tool '{tool_name}' is not permitted for role "
                    f"'{agent_type.value}' in registry"
                )
                raise ValueError(error_message)

    return AgentProfile(
        agent_type=agent_type,
        name=name or agent_type.value,
        system_prompt=prompt,
        allowed_tools=allowed_tools,
        model_alias=model_alias,
    )
