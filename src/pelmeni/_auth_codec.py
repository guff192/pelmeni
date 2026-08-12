"""Private credential codec collaborator for pelmeni auth module."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pydantic import ValidationError

from pelmeni._auth_codec_helpers import CredentialValueFormatter

REPLACE_OLD = "-"
REPLACE_NEW = "_"


class CredentialCodec:
    """Collaborator for auth codec operation."""

    def __init__(
        self,
        formatter: CredentialValueFormatter | None = None,
    ) -> None:
        """Initialize CredentialCodec."""
        self.formatter = (
            CredentialValueFormatter() if formatter is None else formatter
        )

    def normalize_provider(self, provider: str) -> str:
        """Normalize provider name string."""
        return provider.lower().replace(REPLACE_OLD, REPLACE_NEW)

    def format_validation_error(self, exc: ValidationError) -> str:
        """Format validation error messages."""
        return self.formatter.format_validation_error(exc)

    def format_value(self, raw_value: object) -> str:
        """Format individual python object to TOML value string."""
        return self.formatter.format_value(raw_value)

    def encode_toml(self, cred_store: dict[str, dict[str, Any]]) -> str:
        """Serialize data dictionary into TOML string format."""
        return self.formatter.encode_toml(cred_store)
