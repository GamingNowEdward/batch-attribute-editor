"""Result data models: preview report and apply report (pure data, suitable for UI display and
test assertions)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.compatibility import (
    NodeValidation,
    ValidationStatus,
    status_label,
)
from core.types import ChannelSpec
from utils.logging_utils import OperationLog, plural


def format_value(value: Any) -> str:
    """Compact one-value formatting shared by previews and reports.

    ``None`` renders as an em dash so "no current value could be read" is visible
    at a glance instead of hiding behind a literal ``None``.
    """
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, float):
        text = f"{value:.6f}".rstrip("0").rstrip(".")
        return text if text not in ("", "-") else "0"
    return str(value)


@dataclass
class ChannelChange:
    """A change that is about to happen on one channel."""

    channel: ChannelSpec
    value: Any
    target: str = ""            # Full write target, e.g. |GRP|CubeA.translateX
    current: Any = None         # Current value (None when the read failed)

    @property
    def label(self) -> str:
        return self.channel.display_label

    def describe_change(self) -> str:
        """One-line change description: ``Value: 1 → 18``."""
        return (f"{self.channel.display_label}: "
                f"{format_value(self.current)} → {format_value(self.value)}")


@dataclass
class PreviewItem:
    """One row in the preview (one node)."""

    validation: NodeValidation
    changes: Tuple[ChannelChange, ...] = ()

    @property
    def node_name(self) -> str:
        return self.validation.node_name

    @property
    def display_name(self) -> str:
        return self.validation.display_name

    @property
    def will_modify(self) -> bool:
        return bool(self.changes)

    @property
    def skip_reason(self) -> str:
        if self.will_modify:
            blocked = self.validation.blocked_channels
            if blocked:
                return "Some channels skipped: " + ", ".join(
                    dict.fromkeys(state.reason for state in blocked if state.reason)
                )
            return ""
        return self.validation.skip_reason()


@dataclass
class PreviewReport:
    """Preview before a batch edit (requirement section 21)."""

    attribute_name: str = ""
    type_label: str = ""
    value_repr: str = ""
    items: List[PreviewItem] = field(default_factory=list)
    counts: Dict[ValidationStatus, int] = field(default_factory=dict)
    other_type_total: int = 0
    elapsed: float = 0.0

    @property
    def will_modify(self) -> int:
        return sum(1 for item in self.items if item.will_modify)

    @property
    def skipped(self) -> int:
        return sum(1 for item in self.items if not item.will_modify)

    @property
    def partial(self) -> int:
        """Number of nodes that are modified but have other channels skipped."""
        return sum(
            1 for item in self.items
            if item.will_modify and item.validation.blocked_channels
        )

    @property
    def channel_writes(self) -> int:
        """Number of channels actually written (node count × writable channels per node)."""
        return sum(len(item.changes) for item in self.items)

    def count(self, status: ValidationStatus) -> int:
        return self.counts.get(status, 0)

    def skip_summary(self) -> str:
        """Summary of skip reasons, e.g. "8 Locked, 3 Missing"."""
        parts: List[str] = []
        for status in (
            ValidationStatus.LOCKED,
            ValidationStatus.CONNECTED,
            ValidationStatus.MISSING,
            ValidationStatus.TYPE_MISMATCH,
            ValidationStatus.NOT_WRITABLE,
            ValidationStatus.CHANNEL_MISSING,
            ValidationStatus.NODE_MISSING,
            ValidationStatus.UNSUPPORTED,
        ):
            value = self.count(status)
            if value:
                parts.append(f"{value} {status_label(status)}")
        return ", ".join(parts)

    def describe(self) -> str:
        """One-line summary."""
        text = (f"Will modify {plural(self.will_modify, 'node')} "
                f"({plural(self.channel_writes, 'channel')}), skip {self.skipped}")
        if self.partial:
            text += f", {plural(self.partial, 'node')} with partially skipped channels"
        detail = self.skip_summary()
        if detail:
            text += f"\nSkip reasons: {detail}"
        if self.other_type_total:
            text += (f"\n{plural(self.other_type_total, 'node')} with the same attribute name "
                     f"but a different type (excluded)")
        return text

    def modify_names(self, limit: int = 500) -> List[str]:
        """List of node names that will be modified (requirement section 21)."""
        names = [item.display_name for item in self.items if item.will_modify]
        return names[:limit]

    # ------------------------------------------------------------ detailed preview

    def change_lines(self, limit: int = 500) -> List[str]:
        """One line per changed channel: ``<node>   Value: old → new``."""
        lines: List[str] = []
        hidden = 0
        for item in self.items:
            if not item.will_modify:
                continue
            for change in item.changes:
                if len(lines) >= limit:
                    hidden += 1
                    continue
                lines.append(f"{item.display_name}   {change.describe_change()}")
        if hidden:
            lines.append(f"... {plural(hidden, 'more change')}")
        return lines

    def skipped_lines(self, limit: int = 200) -> List[str]:
        """One line per fully skipped node with its reason."""
        lines: List[str] = []
        hidden = 0
        for item in self.items:
            if item.will_modify:
                continue
            if len(lines) >= limit:
                hidden += 1
                continue
            reason = item.skip_reason or "skipped"
            lines.append(f"{item.display_name}   {reason}")
        if hidden:
            lines.append(f"... {plural(hidden, 'more skipped node')}")
        return lines

    def detail_text(self) -> str:
        """Full preview detail: the change list plus the skip list.

        This is what the Preview panel shows instead of a bare node-name list, so
        the user can see the actual old → new values and every skip reason before
        anything is written.
        """
        chunks: List[str] = []
        changes = self.change_lines()
        if changes:
            chunks.append("── Will modify ──")
            chunks.extend(changes)
        skipped = self.skipped_lines()
        if skipped:
            if chunks:
                chunks.append("")
            chunks.append("── Skipped ──")
            chunks.extend(skipped)
        return "\n".join(chunks)


@dataclass
class ApplyItemResult:
    """Write result of a single channel."""

    node_name: str
    channel_label: str
    target: str
    success: bool
    value: Any = None
    old_value: Any = None
    error: str = ""
    detail: str = ""


@dataclass
class ApplyReport:
    """Result report of a batch edit (requirement section 22)."""

    attribute_name: str = ""
    type_label: str = ""
    value_repr: str = ""
    items: List[ApplyItemResult] = field(default_factory=list)
    log: OperationLog = field(default_factory=OperationLog)
    chunk_name: str = ""
    elapsed: float = 0.0
    skipped_count: int = 0

    @property
    def succeeded(self) -> int:
        return sum(1 for item in self.items if item.success)

    @property
    def failed(self) -> int:
        return sum(1 for item in self.items if not item.success and item.error)

    @property
    def touched_nodes(self) -> int:
        """Number of successfully modified nodes (de-duplicated)."""
        return len({item.node_name for item in self.items if item.success})

    def describe(self) -> str:
        """One-line summary."""
        text = f"Succeeded:{self.succeeded}"
        if self.skipped_count:
            text += f"  Skipped:{self.skipped_count}"
        text += f"  Failed:{self.failed}"
        if self.touched_nodes:
            text += f"  ({plural(self.touched_nodes, 'node')} touched)"
        if self.elapsed:
            text += f"  Elapsed {self.elapsed * 1000:.0f} ms"
        return text

    def failures(self) -> List[ApplyItemResult]:
        return [item for item in self.items if not item.success and item.error]
