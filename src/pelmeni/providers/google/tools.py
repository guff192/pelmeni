"""Google Gemini tool translator."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

_KEY_FUNCTION_DECLARATIONS = "functionDeclarations"
_KEY_NAME = "name"
_KEY_TYPE = "type"
_KEY_FUNCTION = "function"
_KEY_DESCRIPTION = "description"
_KEY_PARAMETERS = "parameters"
_TYPE_FUNCTION = "function"


class GoogleToolTranslator:
    """Translator for tool declarations to Gemini format."""

    def convert_tools(
        self, tools: Sequence[dict[str, Any]] | None
    ) -> list[dict[str, Any]] | None:
        """Convert tools list to function declarations format."""
        if not tools:
            return None
        declarations = self._extract_declarations(tools)
        if not declarations:
            return None
        return [{_KEY_FUNCTION_DECLARATIONS: declarations}]

    def _extract_declarations(
        self, tools: Sequence[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        declarations: list[dict[str, Any]] = []
        for tool_item in tools:
            if self._is_function_tool(tool_item):
                declarations.append(self._convert_function_tool(tool_item))
            else:
                declarations.append(tool_item)
        return declarations

    def _is_function_tool(self, tool_item: dict[str, Any]) -> bool:
        return (
            _KEY_TYPE in tool_item and tool_item[_KEY_TYPE] == _TYPE_FUNCTION
        )

    def _convert_function_tool(
        self, tool_item: dict[str, Any]
    ) -> dict[str, Any]:
        has_fn = _KEY_FUNCTION in tool_item and isinstance(
            tool_item[_KEY_FUNCTION], dict
        )
        function_spec = tool_item[_KEY_FUNCTION] if has_fn else {}
        declaration: dict[str, Any] = {
            _KEY_NAME: self._extract_string(function_spec, _KEY_NAME),
            _KEY_DESCRIPTION: self._extract_string(
                function_spec, _KEY_DESCRIPTION
            ),
        }
        parameters_value = function_spec.get(_KEY_PARAMETERS)
        if parameters_value is not None:
            declaration[_KEY_PARAMETERS] = parameters_value
        return declaration

    def _extract_string(
        self, spec: dict[str, Any], key_name: str
    ) -> str:
        string_val = spec.get(key_name)
        if isinstance(string_val, str):
            return string_val
        return ""
