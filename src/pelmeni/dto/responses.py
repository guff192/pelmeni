"""Data transfer objects for chat responses."""

from pydantic import BaseModel, ConfigDict

# Runtime import (not TYPE_CHECKING): pydantic resolves field types at
# model build time, so moving this under TYPE_CHECKING would break ChatResponse.
from pelmeni.dto.messages import AssistantMessage  # noqa: TC001


class Choice(BaseModel):
    """Mirroring provider.py:18 message extraction."""

    message: AssistantMessage


class ChatResponse(BaseModel):
    """Mirroring provider.py:18 raw JSON pass-through structure."""

    choices: list[Choice]
    model_config = ConfigDict(extra="allow")
