"""Tests for domain AgentProfile and role prompt loader."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from pelmeni.domain import (
    AGENT_TOOL_WHITELISTS,
    BASE_SYSTEM_PROMPTS,
    AgentProfile,
    AgentType,
    get_agent_profile,
    load_agent_prompt,
)
from pelmeni.dto.tools import AgentRole
from pelmeni.tools.registry import DEFAULT_REGISTRY, ToolRegistry

if TYPE_CHECKING:
    from pathlib import Path


def test_agent_type_enum_values() -> None:
    """Verify all five agent types conform to CONTEXT.md terminology."""
    expected = {"manager", "investigator", "builder", "reviewer", "tester"}
    assert {agent_type.value for agent_type in AgentType} == expected


def test_agent_role_has_manager() -> None:
    """AgentRole enum in DTO includes MANAGER for tool registry access."""
    assert AgentRole.MANAGER.value == "manager"


def test_default_registry_includes_manager_read_tool() -> None:
    """DEFAULT_REGISTRY grants read tool access to Manager."""
    assert DEFAULT_REGISTRY.is_tool_allowed(AgentRole.MANAGER, "read")
    assert not DEFAULT_REGISTRY.is_tool_allowed(AgentRole.MANAGER, "write")
    assert not DEFAULT_REGISTRY.is_tool_allowed(AgentRole.MANAGER, "bash")


def test_agent_profile_dataclass_fields() -> None:
    """AgentProfile encapsulates static profile attributes."""
    profile = AgentProfile(
        agent_type=AgentType.BUILDER,
        name="builder",
        system_prompt="You are a builder.",
        allowed_tools=("read", "edit", "write", "bash"),
        model_alias="worker",
    )
    assert profile.agent_type == AgentType.BUILDER
    assert profile.name == "builder"
    assert profile.system_prompt == "You are a builder."
    assert profile.allowed_tools == ("read", "edit", "write", "bash")
    assert profile.model_alias == "worker"

    with pytest.raises(AttributeError):
        profile.name = "mutated"  # type: ignore[misc]


def test_baseline_system_prompts_cover_all_agent_types() -> None:
    """Baseline system prompts exist for all five agent types."""
    for agent_type in AgentType:
        prompt = BASE_SYSTEM_PROMPTS.get(agent_type)
        assert prompt is not None
        assert len(prompt.strip()) > 0
        assert agent_type.value in prompt.lower()


def test_agent_tool_whitelists_match_registry() -> None:
    """Agent tool whitelists match DEFAULT_REGISTRY whitelists."""
    for agent_type in AgentType:
        whitelisted = AGENT_TOOL_WHITELISTS[agent_type]
        for tool_name in whitelisted:
            assert DEFAULT_REGISTRY.is_tool_allowed(agent_type.value, tool_name)


def test_prompt_loader_uses_baseline_when_no_override(tmp_path: Path) -> None:
    """Prompt loader returns built-in baseline when no file exists."""
    config_dir = tmp_path / ".config/pelmeni/agents"
    prompt = load_agent_prompt(AgentType.INVESTIGATOR, config_dir=config_dir)
    assert prompt == BASE_SYSTEM_PROMPTS[AgentType.INVESTIGATOR]


def test_prompt_loader_overrides_when_file_exists(tmp_path: Path) -> None:
    """Prompt loader reads markdown template override when present."""
    config_dir = tmp_path / ".config/pelmeni/agents"
    config_dir.mkdir(parents=True, exist_ok=True)
    override_file = config_dir / "investigator.md"
    override_content = "# Custom Investigator Prompt\nOnly inspect tests."
    override_file.write_text(override_content, encoding="utf-8")

    prompt = load_agent_prompt(AgentType.INVESTIGATOR, config_dir=config_dir)
    assert prompt == override_content


def test_get_agent_profile_with_registry_validation(tmp_path: Path) -> None:
    """Profile resolution validates tool whitelists against registry."""
    config_dir = tmp_path / ".config/pelmeni/agents"
    profile = get_agent_profile(
        AgentType.BUILDER,
        model_alias="worker",
        config_dir=config_dir,
        registry=DEFAULT_REGISTRY,
    )
    assert profile.agent_type == AgentType.BUILDER
    assert profile.model_alias == "worker"
    assert profile.allowed_tools == ("read", "edit", "write", "bash")
    assert profile.system_prompt == BASE_SYSTEM_PROMPTS[AgentType.BUILDER]


def test_get_agent_profile_rejects_unregistered_tools() -> None:
    """Profile resolution raises ValueError if tools exceed registry."""
    empty_registry = ToolRegistry()
    with pytest.raises(ValueError, match="not permitted"):
        get_agent_profile(
            AgentType.INVESTIGATOR,
            model_alias="worker",
            registry=empty_registry,
        )
