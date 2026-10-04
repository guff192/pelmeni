"""Pure domain agent types enum."""

from enum import StrEnum


class AgentType(StrEnum):
    """Supported agent types per domain terminology."""

    MANAGER = "manager"
    INVESTIGATOR = "investigator"
    BUILDER = "builder"
    REVIEWER = "reviewer"
    TESTER = "tester"
