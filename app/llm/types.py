from dataclasses import dataclass, field
from typing import Any


class LLMError(RuntimeError):
    """A model provider failed in a way the caller may want to recover from."""


class ToolBudgetExceededError(LLMError):
    """The tool-call loop hit its cap. Falling over to another model would
    re-run every business call, bill those APIs twice, and fail on the same
    limit. The orchestrator must not treat this as a fallback trigger.
    """


@dataclass
class AssistantReply:
    text: str
    provider: str
    successful_tools: set[str] = field(default_factory=set)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    fallback_used: bool = False
