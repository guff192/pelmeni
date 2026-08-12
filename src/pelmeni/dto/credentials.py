"""Data transfer objects for provider credentials."""


from pydantic import BaseModel, SecretStr


class ApiKeyCredentials(BaseModel):
    """Credentials for providers authenticated with an API key."""

    provider: str
    api_key: SecretStr


class OAuthCredentials(BaseModel):
    """Credentials for providers authenticated with OAuth."""

    provider: str
    access_token: SecretStr
    refresh_token: SecretStr
    expires_at: int


class NoCredentials(BaseModel):
    """Credentials marker for providers that require no authentication."""

    provider: str


Credentials = ApiKeyCredentials | OAuthCredentials | NoCredentials
