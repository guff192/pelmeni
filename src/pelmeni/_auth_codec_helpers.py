"""Private helper for credential formatting, escaping, and encoding."""

from __future__ import annotations

from typing import Any

from pydantic import SecretStr, ValidationError

BACKSLASH = "\\"
DOUBLE_QUOTE = '"'
ESCAPED_BACKSLASH = r"\\"
ESCAPED_DOUBLE_QUOTE = r'\"'
EMPTY_STR_REPR = '""'
BOOL_TRUE = "true"
BOOL_FALSE = "false"
FIELD_MSG_DEFAULT = "invalid field"
PATH_SEP = "."
DETAILS_SEP = "; "
KEY_VAL_SEP = " = "
LINE_SEP = "\n"


class CredentialValueFormatter:
    """Helper for auth codec validation error formatting and scalar encoding."""

    def format_validation_error(self, exc: ValidationError) -> str:
        """Format validation error messages."""
        details: list[str] = []
        for err in exc.errors(include_input=False):
            loc_str = PATH_SEP.join(str(loc_entry) for loc_entry in err["loc"])
            msg = err.get("msg", FIELD_MSG_DEFAULT)
            details.append(f"{loc_str}: {msg}")
        return DETAILS_SEP.join(details)

    def format_value(self, raw_value: object) -> str:
        """Format individual python object to TOML value string."""
        if isinstance(raw_value, bool):
            return BOOL_TRUE if raw_value else BOOL_FALSE
        if isinstance(raw_value, (int, float)):
            return str(raw_value)
        if raw_value is None:
            return EMPTY_STR_REPR
        return self._format_string_value(raw_value)

    def encode_toml(self, cred_store: dict[str, dict[str, Any]]) -> str:
        """Serialize data dictionary into TOML string format."""
        lines: list[str] = []
        for section_key, cred_dict in cred_store.items():
            lines.append(f"[{section_key}]")
            for setting_key, setting_val in cred_dict.items():
                if setting_val is not None:
                    lines.append(
                        f"{setting_key}{KEY_VAL_SEP}"
                        f"{self.format_value(setting_val)}"
                    )
            lines.append("")
        return LINE_SEP.join(lines)

    def _format_string_value(self, raw_value: object) -> str:
        """Format string/SecretStr/fallback to escaped double quotes."""
        text_content = (
            raw_value.get_secret_value()
            if isinstance(raw_value, SecretStr)
            else str(raw_value)
        )
        escaped_content = text_content.replace(
            BACKSLASH, ESCAPED_BACKSLASH
        ).replace(DOUBLE_QUOTE, ESCAPED_DOUBLE_QUOTE)
        return f"{DOUBLE_QUOTE}{escaped_content}{DOUBLE_QUOTE}"
