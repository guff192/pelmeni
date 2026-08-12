"""Secure TOML credential storage."""

from __future__ import annotations

import os
import tempfile
import tomllib
from pathlib import Path
from typing import Any


class CredentialStoreError(Exception):
    """Raised when the credential store cannot be read or written safely."""


class TomlCredentialStore:
    """Load and save credentials in a private TOML file."""

    _PRIVATE_MODE = 0o600  # noqa: WPS115

    def __init__(self, path: Path) -> None:
        """Initialize the store at ``path``."""
        self._path = path

    def load(self) -> dict[str, Any]:
        """Load the credential tables from disk."""
        if self._path.is_symlink():
            error_message = "Credential file must not be a symlink"
            raise CredentialStoreError(error_message)
        if not self._path.exists():
            return {}
        self._enforce_permissions()
        try:
            with self._path.open("rb") as credential_file:
                stored_data = tomllib.load(credential_file)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            error_message = f"Unable to read credentials: {exc}"
            raise CredentialStoreError(error_message) from exc
        return stored_data

    def save(self, credentials: dict[str, dict[str, Any]]) -> None:
        """Atomically save credential tables with mode 0600."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            dir=self._path.parent,
            prefix=f".{self._path.name}.",  # noqa: WPS237
        )
        temporary_path = Path(temporary_name)
        try:  # noqa: WPS229
            os.fchmod(file_descriptor, self._PRIVATE_MODE)
            with os.fdopen(file_descriptor, "w", encoding="utf-8") as stream:
                stream.write(self._encode(credentials))
                stream.flush()
                os.fsync(stream.fileno())
            temporary_path.replace(self._path)
            self._path.chmod(self._PRIVATE_MODE)
        except OSError as exc:
            temporary_path.unlink(missing_ok=True)
            error_message = f"Unable to write credentials: {exc}"
            raise CredentialStoreError(error_message) from exc

    def _enforce_permissions(self) -> None:
        current_mode = self._path.stat().st_mode & 0o777  # noqa: WPS432
        if current_mode != self._PRIVATE_MODE:
            self._path.chmod(self._PRIVATE_MODE)

    @classmethod
    def _encode(cls, credentials: dict[str, dict[str, Any]]) -> str:
        sections = []
        for provider, values in credentials.items():  # noqa: WPS110
            sections.append(f"[{cls._quote(provider)}]")
            for field_name, field_value in values.items():
                sections.append(
                    f"{field_name} = {cls._format_value(field_value)}",
                )
            sections.append("")
        return "\n".join(sections)

    @staticmethod
    def _quote(value: str) -> str:  # noqa: WPS110, WPS602
        escaped_slashes = value.replace("\\", "\\\\")  # noqa: WPS342
        escaped_value = escaped_slashes.replace('"', '\\"')  # noqa: WPS342
        return f'"{escaped_value}"'

    @classmethod
    def _format_value(cls, value: object) -> str:  # noqa: WPS110
        if isinstance(value, bool):
            return str(value).lower()
        if isinstance(value, (int, float)):
            return str(value)
        secret_value = getattr(value, "get_secret_value", None)
        if secret_value is not None:
            value = secret_value()  # noqa: WPS110
        return cls._quote(str(value))
