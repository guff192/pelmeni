"""OAuth flow interfaces."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pelmeni.dto.credentials import OAuthCredentials


class OAuthFlow(ABC):
    """Interface implemented by provider OAuth flows."""

    @abstractmethod
    def login(self) -> OAuthCredentials:
        """Run an interactive OAuth login and return credentials."""

    @abstractmethod
    def refresh(self, refresh_token: str) -> OAuthCredentials:
        """Refresh credentials using a refresh token."""
