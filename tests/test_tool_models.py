"""Tests for role-aware tool models and registration."""

from __future__ import annotations

from pelmeni.config.models import AgentModelSchema
from pelmeni.dto.tools import AgentRole, ToolParameterSchema, ToolSpec
from pelmeni.tools import ToolRegistry


def _tool(name: str = "read_file") -> ToolSpec:
    """Build a representative tool specification."""
    return ToolSpec(
        name=name,
        description="Read a file from disk.",
        parameters=ToolParameterSchema(
            properties={
                "path": {
                    "type": "string",
                    "description": "Path to the file.",
                },
            },
            required=["path"],
        ),
    )


def test_agent_role_values() -> None:
    """Agent roles expose the stable wire values used by configuration."""
    assert {role.value for role in AgentRole} == {
        "investigator",
        "builder",
        "reviewer",
        "tester",
    }
    assert AgentRole.INVESTIGATOR == "investigator"
    assert AgentRole.BUILDER == "builder"
    assert AgentRole.REVIEWER == "reviewer"
    assert AgentRole.TESTER == "tester"


def test_tool_parameter_schema_defaults_to_object() -> None:
    """Parameter schemas represent JSON object schemas."""
    parameters = ToolParameterSchema()

    assert parameters.type == "object"
    assert parameters.properties == {}
    assert parameters.required == []


def test_tool_spec_serializes_parameter_schema() -> None:
    """Tool specifications preserve metadata and nested parameter details."""
    tool = _tool()

    assert tool.name == "read_file"
    assert tool.description == "Read a file from disk."
    assert tool.model_dump() == {
        "name": "read_file",
        "description": "Read a file from disk.",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the file.",
                },
            },
            "required": ["path"],
        },
    }


def test_registry_returns_tools_registered_for_role() -> None:
    """A role receives only the tools explicitly registered for it."""
    registry = ToolRegistry()
    shared_tool = _tool("read_file")
    builder_tool = _tool("write_file")
    registry.register(
        shared_tool,
        roles=[AgentRole.INVESTIGATOR, AgentRole.BUILDER],
    )
    registry.register(builder_tool, roles=[AgentRole.BUILDER])

    assert registry.get_tools_for_role(AgentRole.INVESTIGATOR) == [shared_tool]
    assert registry.get_tools_for_role(AgentRole.BUILDER) == [
        shared_tool,
        builder_tool,
    ]
    assert registry.get_tools_for_role(AgentRole.REVIEWER) == []


def test_registry_reports_tool_permission_by_name() -> None:
    """Tool permission checks use both role and registered tool name."""
    registry = ToolRegistry()
    registry.register(_tool("read_file"), roles=[AgentRole.INVESTIGATOR])

    assert registry.is_tool_allowed(AgentRole.INVESTIGATOR, "read_file") is True
    assert registry.is_tool_allowed(AgentRole.BUILDER, "read_file") is False
    assert registry.is_tool_allowed(AgentRole.INVESTIGATOR, "missing") is False

def test_registry_is_tool_allowed_unknown_role() -> None:
    """Checking tool allowance for unknown role string does not raise error."""
    registry = ToolRegistry()
    registry.register(_tool("read_file"), roles=[AgentRole.INVESTIGATOR])

    assert registry.is_tool_allowed("worker", "read_file") is False
    assert registry.is_tool_allowed("worker", "missing") is False

def test_agent_model_schema_accepts_tool_names() -> None:
    """Agent model configuration can opt into a list of named tools."""
    schema = AgentModelSchema(
        model="fast",
        tools=["read_file", "search"],
    )

    assert schema.model == "fast"
    assert schema.tools == ["read_file", "search"]


def test_agent_model_schema_tools_are_optional() -> None:
    """Existing model-only agent configuration remains valid."""
    schema = AgentModelSchema(model="fast")

    assert schema.tools == []
