"""Credential redaction for traces and training examples.

Business fields stay. A leaked token in a training checkpoint stays leaked
in every future model, so only credentials are stripped.
"""

import re
from typing import Any

DEFAULT_TEXT_LIMIT = 20_000
REDACTED = "[REDACTED]"

_TOKEN_PATTERN = re.compile(
    r"\b(?:xox[baprs]-[A-Za-z0-9-]+|sk-[A-Za-z0-9_-]{16,}|"
    r"sk-ant-[A-Za-z0-9_-]{16,}|ghp_[A-Za-z0-9]{20,}|"
    r"AIza[A-Za-z0-9_-]{20,}|EAA[A-Za-z0-9]{40,})\b"
)
_LABELED_SECRET_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret)\s*[:=]\s*([^\s,;]+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)(\S+)")
_JSON_SECRET_PATTERN = re.compile(
    r'(?i)("(?:[a-z0-9_-]*(?:api[_-]?key|token|password|secret|credential)'
    r'[a-z0-9_-]*)"\s*:\s*)"[^"]*"'
)
SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|bearer|password|"
    r"secret|credential|private[_-]?key|signature|authorization)"
)


def redact_text(value: str, *, limit: int | None = DEFAULT_TEXT_LIMIT) -> str:
    result = _TOKEN_PATTERN.sub(REDACTED, value)
    result = _JSON_SECRET_PATTERN.sub(rf'\1"{REDACTED}"', result)
    result = _LABELED_SECRET_PATTERN.sub(rf"\1={REDACTED}", result)
    result = _BEARER_PATTERN.sub(rf"\1{REDACTED}", result)
    if limit is None:
        return result
    return result[:limit]


def redact_json(value: Any, *, depth: int = 0) -> Any:
    if depth > 12:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            name = str(key)
            if SENSITIVE_KEY_PATTERN.search(name):
                redacted[name] = REDACTED
            else:
                redacted[name] = redact_json(item, depth=depth + 1)
        return redacted
    if isinstance(value, (list, tuple)):
        return [redact_json(item, depth=depth + 1) for item in value]
    if isinstance(value, str):
        return redact_text(value, limit=None)
    return value
