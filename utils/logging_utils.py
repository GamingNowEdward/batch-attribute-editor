"""Dual-channel logging: the UI shows information the user can understand, while
technical details are kept separately.

Design goal (corresponding to the "error handling" requirement): never silently
swallow exceptions. Every failure record carries both
* a one-sentence user-facing reason
* technical details for the TD (node, plug, exception type and message)
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Iterable, List, Optional


class LogLevel(enum.Enum):
    """Log level."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


@dataclass
class LogEntry:
    """A single log entry."""

    level: LogLevel
    message: str
    detail: str = ""
    node: str = ""
    attribute: str = ""

    def format_line(self) -> str:
        target = ""
        if self.node:
            target = f"{self.node}.{self.attribute}" if self.attribute else self.node
        head = f"[{self.level.value.upper()}]"
        if target:
            return f"{head} {target}: {self.message}"
        return f"{head} {self.message}"


@dataclass
class OperationLog:
    """The log entry collection of one operation."""

    title: str = ""
    entries: List[LogEntry] = field(default_factory=list)

    def _add(self, level: LogLevel, message: str, node: str = "", attribute: str = "",
             detail: str = "") -> LogEntry:
        entry = LogEntry(level=level, message=message, detail=detail, node=node, attribute=attribute)
        self.entries.append(entry)
        return entry

    def info(self, message: str, node: str = "", attribute: str = "", detail: str = "") -> LogEntry:
        return self._add(LogLevel.INFO, message, node, attribute, detail)

    def warning(self, message: str, node: str = "", attribute: str = "", detail: str = "") -> LogEntry:
        return self._add(LogLevel.WARNING, message, node, attribute, detail)

    def error(self, message: str, node: str = "", attribute: str = "",
              detail: str = "") -> LogEntry:
        return self._add(LogLevel.ERROR, message, node, attribute, detail)

    def extend(self, other: "OperationLog") -> None:
        self.entries.extend(other.entries)

    @property
    def warnings(self) -> List[LogEntry]:
        return [e for e in self.entries if e.level is LogLevel.WARNING]

    @property
    def errors(self) -> List[LogEntry]:
        return [e for e in self.entries if e.level is LogLevel.ERROR]

    def count(self, level: LogLevel) -> int:
        return sum(1 for e in self.entries if e.level is level)

    def is_empty(self) -> bool:
        return not self.entries

    def ui_text(self, limit: int = 400) -> str:
        """User-facing text: only the message lines, truncated when too long."""
        lines = [e.format_line() for e in self.entries]
        if len(lines) > limit:
            hidden = len(lines) - limit
            lines = lines[:limit] + [f"... {hidden} more entries"]
        return "\n".join(lines)

    def technical_text(self, limit: int = 2000) -> str:
        """TD-facing text: includes detail and target information."""
        chunks: List[str] = []
        if self.title:
            chunks.append(f"# {self.title}")
        for entry in self.entries[:limit]:
            chunks.append(entry.format_line())
            if entry.detail:
                chunks.append(f"    detail: {entry.detail}")
        if len(self.entries) > limit:
            chunks.append(f"... {len(self.entries) - limit} more entries")
        return "\n".join(chunks)


def describe_exception(exc: BaseException) -> str:
    """Turn an exception into a stable technical description string."""
    text = str(exc).strip().replace("\n", " ")
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def merge_reasons(reasons: Iterable[str]) -> str:
    """Merge multiple reasons into one readable line (first-seen order, de-duplicated)."""
    seen: List[str] = []
    for reason in reasons:
        if reason and reason not in seen:
            seen.append(reason)
    return ", ".join(seen)


def plural(count: int, singular: str, plural_form: Optional[str] = None) -> str:
    """Render ``<count> <noun>`` with correct pluralisation.

    Delegates to the localization manager so a user-visible report can be
    rendered in any supported language; the English pluralisation below is the
    fallback kept for unknown nouns (identical to the historical behaviour).

    >>> plural(1, "node")
    '1 node'
    >>> plural(0, "node")
    '0 nodes'
    >>> plural(2, "intermediate", "intermediates")
    '2 intermediates'
    """
    from i18n import plural as localized_plural

    return localized_plural(count, singular, plural_form)
