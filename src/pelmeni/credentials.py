"""Credential models for pelmeni authentication.

No agent SDKs. Python 3.14. Raw httpx + Pydantic. 80-column limit.
"""

from __future__ import annotations

import math
import time
from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    TypeAdapter,
)

CREDENTIALS_PATH = Path.home() / ".config" / "pelmeni" / "credentials.toml"


class ApiKeyCredentials(BaseModel):
    """API key credential."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    type: Literal["api_key"] = "api_key"
    api_key: SecretStr = Field(min_length=1)


class OAuthCredentials(BaseModel):
    """OAuth 2.0 credential with device-flow refresh support."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    type: Literal["oauth"] = "oauth"
    access_token: SecretStr = Field(min_length=1)
    refresh_token: SecretStr | None = Field(default=None, min_length=1)
    expires_at: float | None = Field(default=None, gt=0)
    client_id: str = Field(min_length=1)
    client_secret: SecretStr | None = Field(default=None, min_length=1)
    token_type: str = Field(default="Bearer", min_length=1)

    def is_expired(self, buffer_seconds: float = 60.0) -> bool:
        """Check if access token is expired or about to expire."""
        if self.expires_at is None or math.isnan(self.expires_at):
            return False
        return time.time() + buffer_seconds >= self.expires_at


class NoCredentials(BaseModel):
    """Explicit none/anonymous credentials."""

    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)

    type: Literal["none"] = "none"


Credentials = Annotated[
    ApiKeyCredentials | OAuthCredentials | NoCredentials,
    Field(discriminator="type"),
]

_CREDENTIALS_ADAPTER: TypeAdapter[Credentials] = TypeAdapter(Credentials)
