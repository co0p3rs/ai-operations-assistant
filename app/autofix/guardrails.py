"""Boundaries the repair agent cannot cross, whatever the model decides."""

from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

UNREADABLE_PATTERNS: tuple[str, ...] = (
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    ".git/*",
)

UNWRITABLE_PATTERNS: tuple[str, ...] = UNREADABLE_PATTERNS + (
    ".github/*",
    "app/autofix/*",
    "app/redaction.py",
    "compose.yaml",
    "Dockerfile",
    "requirements.txt",
    "requirements-dev.txt",
)


class GuardrailError(RuntimeError):
    """Raised when a requested path or budget is out of bounds."""


@dataclass(frozen=True)
class AutofixLimits:
    max_tool_rounds: int = 24
    max_changed_files: int = 12
    max_write_chars: int = 60_000
    max_read_lines: int = 400
    max_test_runs: int = 4


def _matches(relative: str, patterns: tuple[str, ...]) -> bool:
    return any(fnmatch(relative, pattern) for pattern in patterns)


def resolve_in_repo(root: Path, candidate: str) -> Path:
    cleaned = (candidate or "").strip().replace("\\", "/").lstrip("/")
    if not cleaned:
        raise GuardrailError("A path is required")
    resolved_root = root.resolve()
    target = (resolved_root / cleaned).resolve()
    if target != resolved_root and resolved_root not in target.parents:
        raise GuardrailError(f"Path escapes the repository: {candidate}")
    return target


def relative_path(root: Path, target: Path) -> str:
    return target.resolve().relative_to(root.resolve()).as_posix()


def assert_readable(root: Path, candidate: str) -> Path:
    target = resolve_in_repo(root, candidate)
    relative = relative_path(root, target)
    if _matches(relative, UNREADABLE_PATTERNS):
        raise GuardrailError(f"{relative} holds credentials and cannot be read")
    return target


def assert_writable(root: Path, candidate: str) -> Path:
    target = resolve_in_repo(root, candidate)
    relative = relative_path(root, target)
    if _matches(relative, UNWRITABLE_PATTERNS):
        raise GuardrailError(
            f"{relative} is protected; describe the change in the report instead"
        )
    if target.is_dir():
        raise GuardrailError(f"{relative} is a directory")
    return target
