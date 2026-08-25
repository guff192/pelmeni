"""Domain package: pure dataclass models for messages and conversations."""

# messages must be imported first: its bottom-of-module imports load
# rounds and mappers, avoiding circular-import failures if those were
# imported before messages finished initialising.
from pelmeni.domain.message_mappers import (  # noqa: F401
    message_from_dto,
    message_to_dto,
)
from pelmeni.domain.messages import (  # noqa: F401,WPS235
    AssistantMessage,
    Message,
    SystemMessage,
    ToolCall,
    ToolMessage,
    UserMessage,
)
from pelmeni.domain.rounds import Round, group_into_rounds  # noqa: F401
