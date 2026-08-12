"""Private credential permission guard module."""

from __future__ import annotations

import contextlib
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

_DIR_MODE_PRIVATE = 0o700
_FILE_MODE_PRIVATE = 0o600
_POSIX_NAME = "posix"
_PERM_MASK = 0o777
_INSECURE_MASK = 0o77


class CredentialPermissionGuard:
    """Handles directory creation and file permission checks for credentials."""

    dir_mode = _DIR_MODE_PRIVATE
    file_mode = _FILE_MODE_PRIVATE

    def ensure_directory(self, parent: Path) -> None:
        """Ensure parent directory exists with secure permissions."""
        parent.mkdir(mode=self.dir_mode, parents=True, exist_ok=True)
        if os.name == _POSIX_NAME:
            parent.chmod(self.dir_mode)

    def check_file(self, path: Path, error_cls: type[Exception]) -> None:
        """Check file permissions are private (0600 or stricter) on POSIX."""
        if os.name != _POSIX_NAME:
            return
        with contextlib.suppress(OSError):
            st_stat = path.stat()
            mode = st_stat.st_mode & _PERM_MASK
            if mode & _INSECURE_MASK:
                msg = (
                    f"Insecure permissions {oct(mode)} on credentials "
                    f"file {path}. Expected 0600 or stricter."
                )
                raise error_cls(msg)
