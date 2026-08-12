"""Private secure auth file operations module."""

from __future__ import annotations

import contextlib
import os
import time
from typing import TYPE_CHECKING

from pelmeni._auth_permissions import CredentialPermissionGuard

if TYPE_CHECKING:
    from pathlib import Path


class SecureCredentialFile:
    """Handles secure file permissions and atomic writes for credentials."""

    dir_mode = CredentialPermissionGuard.dir_mode
    file_mode = CredentialPermissionGuard.file_mode

    def __init__(
        self, guard: CredentialPermissionGuard | None = None
    ) -> None:
        """Initialize SecureCredentialFile with permission guard."""
        self.guard = (
            CredentialPermissionGuard() if guard is None else guard
        )

    def ensure_directory(self, parent: Path) -> None:
        """Ensure parent directory exists with secure permissions."""
        self.guard.ensure_directory(parent)

    def check_permissions(
        self, path: Path, error_cls: type[Exception]
    ) -> None:
        """Check file permissions are private (0600 or stricter) on POSIX."""
        self.guard.check_file(path, error_cls)

    def write_temp_file(self, tmp_file: Path, file_body: str) -> None:
        """Write content into temporary file descriptor atomically."""
        fd_val = self._open_temp_fd(tmp_file)
        self._write_fd_content(fd_val, file_body)

    def atomic_write(self, path: Path, file_body: str) -> None:
        """Write content to path atomically with private permissions."""
        self.ensure_directory(path.parent)
        process_id = os.getpid()
        time_val = time.time_ns()
        tmp_file = path.parent / f".tmp_{process_id}_{time_val}"
        try:
            self.write_temp_file(tmp_file, file_body)
        except OSError:
            if tmp_file.exists():
                with contextlib.suppress(OSError):
                    tmp_file.unlink()
            raise
        else:
            tmp_file.replace(path)

    def _open_temp_fd(self, tmp_file: Path) -> int:
        """Open temporary file descriptor securely with private mode."""
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        return os.open(tmp_file, flags, self.file_mode)

    def _write_fd_content(self, fd: int, file_body: str) -> None:
        """Write content to open file descriptor and fsync."""
        try:
            stream = os.fdopen(fd, "w", encoding="utf-8")
        except Exception:
            with contextlib.suppress(OSError):
                os.close(fd)
            raise

        with stream:
            stream.write(file_body)
            stream.flush()
            os.fsync(stream.fileno())
