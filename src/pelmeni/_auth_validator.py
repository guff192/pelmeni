"""Stored credential validation helper for pelmeni auth."""

from typing import TYPE_CHECKING

from pydantic import ValidationError

from pelmeni.credentials import _CREDENTIALS_ADAPTER, Credentials

if TYPE_CHECKING:
    from pathlib import Path

    from pelmeni._auth_codec import CredentialCodec
    from pelmeni.auth import AuthError


class StoredCredentialValidator:
    """Validates raw dictionary loaded from store into Credentials."""

    def __init__(
        self,
        path: Path,
        error_cls: type[AuthError],
        codec: CredentialCodec,
    ) -> None:
        """Initialize validator with path, error class, and codec."""
        self.path = path
        self.error_cls = error_cls
        self.codec = codec

    def validate_stored_data(
        self, stored_credentials: dict[str, object]
    ) -> dict[str, Credentials]:
        """Validate raw dictionary loaded from store into Credentials."""
        validated_credentials: dict[str, Credentials] = {}

        for key, raw_entry in stored_credentials.items():
            validated_credentials[key] = self._validate_entry(key, raw_entry)

        return validated_credentials

    def _validate_entry(self, key: str, raw_entry: object) -> Credentials:
        """Validate single entry in stored data table."""
        if not isinstance(raw_entry, dict):
            msg = (
                f"Invalid entry for provider '{key}' in {self.path}: "
                "expected table"
            )
            raise self.error_cls(msg)

        val_copy = dict(raw_entry)
        val_copy.pop("provider", None)

        try:
            return _CREDENTIALS_ADAPTER.validate_python(val_copy)
        except ValidationError as exc:
            sanitized = self.codec.format_validation_error(exc)
            msg = (
                f"Invalid credential entry for '{key}' in {self.path}: "
                f"{sanitized}"
            )
            raise self.error_cls(msg) from exc
