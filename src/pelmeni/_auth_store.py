"""Private secure auth storage module."""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING, Any

from pelmeni._auth_codec import CredentialCodec
from pelmeni._auth_file import SecureCredentialFile

if TYPE_CHECKING:
    from pathlib import Path


class AuthTokenStore:
    """Handles secure loading and atomic saving of credential files."""

    def __init__(
        self,
        path: Path,
        error_cls: type[Exception],
        codec: CredentialCodec | None = None,
        file_ops: SecureCredentialFile | None = None,
    ) -> None:
        """Initialize AuthTokenStore."""
        self.path = path
        self.error_cls = error_cls
        self.codec = CredentialCodec() if codec is None else codec
        self.file_ops = (
            SecureCredentialFile() if file_ops is None else file_ops
        )

    def read_data(self) -> dict[str, Any]:
        """Read and parse raw TOML table from disk."""
        if self.path.is_symlink():
            msg = f"Credential file '{self.path}' is a symlink"
            raise self.error_cls(msg)
        if not self.path.is_file():
            return {}

        self._check_file_permissions(self.path)

        try:
            with self.path.open("rb") as stream:
                return tomllib.load(stream)
        except (OSError, tomllib.TOMLDecodeError) as exc:
            msg = f"Failed to parse credentials TOML at {self.path}: {exc}"
            raise self.error_cls(msg) from exc

    def write_data(self, payload: dict[str, dict[str, Any]]) -> None:
        """Atomically write payload dictionary to disk with 0600 permissions."""
        text = self.codec.encode_toml(payload)
        try:
            self.file_ops.atomic_write(self.path, text)
        except OSError as exc:
            msg = f"Failed to write credentials file {self.path}: {exc}"
            raise self.error_cls(msg) from exc

    def _check_file_permissions(self, path: Path) -> None:
        """Delegate file permission verification to SecureCredentialFile."""
        self.file_ops.check_permissions(path, self.error_cls)
