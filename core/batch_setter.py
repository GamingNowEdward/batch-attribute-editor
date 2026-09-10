"""Batch write: preview and apply.

Measured decisions about the write mechanism (see docs/ARCHITECTURE.md section 6):

* The ``MPlug`` setter **does not enter the Undo queue**, therefore all writes go
  through ``cmds.setAttr``;
* The target name is derived from the real plug structure (``full node path + plug long
  attribute name``); it uses neither the short name (ambiguity when names repeat) nor a
  guessed structure name built by concatenation;
* The whole batch is wrapped in **one Undo Chunk**, therefore edits to 500 nodes occupy
  only one Undo;
* A failure writing a single channel is only logged and then execution continues; it
  never interrupts the whole batch, and it never silently swallows the exception.

Safety policy: Locked / Connected / Missing / incompatible types are always skipped; no
unlock, no breaking connections, no creating array elements, no implicit type
conversion.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from core.compatibility import (
    CompatibilityValidator,
    ValidationStatus,
)
from core.results import (
    ApplyItemResult,
    ApplyReport,
    ChannelChange,
    PreviewItem,
    PreviewReport,
    format_value,
)
from core.search import AggregatedAttribute
from core.traversal import NodeRecord
from core.types import AttributeKind, ChannelSpec
from core.undo import DEFAULT_CHUNK_NAME, UndoManager
from utils.logging_utils import OperationLog, describe_exception

ChannelKey = Tuple[Optional[int], Optional[int]]

_UNSET = object()


class ValueCoercionError(ValueError):
    """The user input cannot be safely converted into the target attribute type."""


def coerce_value(value: Any, kind: AttributeKind) -> Any:
    """Convert user input into a value of the target type.

    This is the **type safety gate**: a String is not treated as a Float, integer input
    goes through strict validation, and float input is not silently rounded. On a failed
    conversion :class:`ValueCoercionError` is raised, to be presented to the user by the
    caller, instead of letting Maya perform an implicit conversion.
    """
    if kind is AttributeKind.STRING:
        return value if isinstance(value, str) else str(value)

    if kind is AttributeKind.BOOL:
        if isinstance(value, str):
            text = value.strip().lower()
            # The Chinese "yes"/"no" input aliases are kept as ASCII escapes so that
            # the accepted input set is byte-identical to before while the source
            # stays free of literal CJK characters.
            if text in ("true", "1", "yes", "on", "\u662f"):
                return True
            if text in ("false", "0", "no", "off", "\u5426"):
                return False
            raise ValueCoercionError(f"Cannot interpret {value!r} as a boolean")
        return bool(value)

    if kind in (AttributeKind.INT, AttributeKind.ENUM):
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if not float(value).is_integer():
                raise ValueCoercionError(f"Integer required, got {value!r}")
            return int(value)
        if isinstance(value, str):
            text = value.strip()
            try:
                return int(text, 10)
            except ValueError as exc:
                raise ValueCoercionError(f"Integer required, got {value!r}") from exc
        raise ValueCoercionError(f"Integer required, got {type(value).__name__}")

    if kind in (AttributeKind.FLOAT, AttributeKind.DOUBLE, AttributeKind.ANGLE,
                AttributeKind.DISTANCE, AttributeKind.TIME):
        if isinstance(value, bool):
            raise ValueCoercionError("A boolean cannot be used as a numeric value")
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            try:
                return float(text)
            except ValueError as exc:
                raise ValueCoercionError(f"Numeric value required, got {value!r}") from exc
        raise ValueCoercionError(f"Numeric value required, got {type(value).__name__}")

    raise ValueCoercionError(f"Unsupported attribute type: {kind.display_name}")


@dataclass
class ValuePayload:
    """The values the user wants to batch write, stored per **channel**.

    One attribute may have several channels (the X/Y/Z of ``translate``, the R/G/B of a
    color, every already existing index of an array), therefore the value cannot be
    represented by a single scalar alone.
    """

    values: Dict[ChannelKey, Any] = field(default_factory=dict)

    def set(self, channel: ChannelSpec, value: Any) -> None:
        """Set the value of one channel (type coercion validation is applied)."""
        self.values[channel.key] = coerce_value(value, channel.kind)

    def set_raw(self, channel: ChannelSpec, value: Any) -> None:
        """Set the value of one channel (a value that has already been coerced)."""
        self.values[channel.key] = value

    def has(self, channel: ChannelSpec) -> bool:
        """Whether the user has set a value for this channel."""
        return channel.key in self.values

    def get(self, channel: ChannelSpec) -> Optional[Any]:
        """Get the channel value; returns None when it has not been set."""
        return self.values.get(channel.key)

    def is_empty(self) -> bool:
        return not self.values

    def describe(self) -> str:
        """Human readable representation of the value, used for reports and the Undo
        Chunk name."""
        if not self.values:
            return ""
        if len(self.values) == 1:
            return format_value(next(iter(self.values.values())))
        return ", ".join(
            f"[{key[0] if key[0] is not None else '-'}."
            f"{key[1] if key[1] is not None else '-'}]={format_value(value)}"
            for key, value in sorted(self.values.items(), key=lambda item: str(item[0]))
        )

    def single_value(self) -> Any:
        """Value of the single channel when there is only one (used for the UI summary)."""
        if len(self.values) == 1:
            return next(iter(self.values.values()))
        return None


def _format_value(value: Any) -> str:
    """Deprecated alias kept for backwards compatibility; use results.format_value."""
    return format_value(value)


class BatchSetter:
    """Batch preview and write."""

    def __init__(self, chunk_name: str = DEFAULT_CHUNK_NAME) -> None:
        self.chunk_name = chunk_name

    # ------------------------------------------------------------ preview

    def preview(self, group: AggregatedAttribute, payload: ValuePayload,
                all_records: Optional[Sequence[NodeRecord]] = None) -> PreviewReport:
        """Build the edit preview: which nodes will be modified, which will be skipped,
        and why.

        :param all_records: **All** nodes within the scan scope. When passed in, the
            preview also covers nodes that do not have this attribute and counts them as
            Missing (requirement section 19: the user needs to see
            "meshShape3 does not exist"). The Apply phase still iterates only over the
            nodes that really have this attribute, therefore it does not produce noisy
            logs for a large number of missing nodes.

        The preview is purely read-only: no writing, no unlocking, no breaking
        connections.
        """
        started = time.perf_counter()
        report = PreviewReport(
            attribute_name=group.name,
            type_label=group.type_label,
            value_repr=payload.describe(),
            other_type_total=group.other_type_total,
        )
        counts: Dict[ValidationStatus, int] = {}
        records = list(all_records) if all_records is not None else list(group.records)

        for record in records:
            validation = CompatibilityValidator.validate(record, group.name, group.definition)

            for status in validation.statuses:
                counts[status] = counts.get(status, 0) + 1

            changes: List[ChannelChange] = []
            for state in validation.channel_states:
                if not state.writable:
                    counts[state.status] = counts.get(state.status, 0) + 1
                    continue
                if not payload.has(state.channel):
                    continue
                target = self.target_for(validation.target_base, state.plug_name)
                changes.append(
                    ChannelChange(
                        channel=state.channel,
                        value=payload.get(state.channel),
                        target=target,
                        current=self.read_value(target),
                    )
                )
            report.items.append(PreviewItem(validation=validation, changes=tuple(changes)))

        report.counts = counts
        report.elapsed = time.perf_counter() - started
        return report

    # ------------------------------------------------------------ apply

    def apply(self, group: AggregatedAttribute, payload: ValuePayload) -> ApplyReport:
        """Apply the batch edit.

        Every target is **re-validated** before writing (whether the node still exists,
        whether the attribute is still valid, whether it is locked/connected, whether the
        type is still compatible), therefore a scene change after the preview can never
        cause a wrong write.
        """
        started = time.perf_counter()
        log = OperationLog(title=f"Batch edit {group.name}")
        report = ApplyReport(
            attribute_name=group.name,
            type_label=group.type_label,
            value_repr=payload.describe(),
            log=log,
            chunk_name=f"{self.chunk_name}: {group.name}",
        )

        undo = UndoManager(report.chunk_name, log)
        with undo:
            for record in group.records:
                if not record.is_alive():
                    report.skipped_count += 1
                    log.warning("Node no longer exists, skipped", node=record.name,
                                attribute=group.name)
                    continue

                validation = CompatibilityValidator.validate(
                    record, group.name, group.definition
                )
                if not validation.has_writable_channel:
                    report.skipped_count += 1
                    log.warning(validation.skip_reason() or "Attribute not writable, skipped",
                                node=record.name, attribute=group.name)
                    continue

                for state in validation.writable_channels:
                    if not payload.has(state.channel):
                        continue
                    target = self.target_for(validation.target_base, state.plug_name)
                    self._write_channel(report, log, record.name, state, target,
                                        payload.get(state.channel))

        report.elapsed = time.perf_counter() - started
        group.invalidate_validation()
        return report

    def _write_channel(self, report: ApplyReport, log: OperationLog, node_name: str,
                       state, target: str, value: Any) -> None:
        """Write a single channel; a failure is only logged and does not affect the other
        targets."""
        old_value = self.read_value(target)
        try:
            self.write_value(target, value, state.channel.kind)
        except Exception as exc:  # noqa: BLE001 - catch all: one failure must not stop the batch
            message = str(exc).strip().splitlines()[0] if str(exc).strip() else type(exc).__name__
            report.items.append(
                ApplyItemResult(
                    node_name=node_name,
                    channel_label=state.channel.display_label,
                    target=target,
                    success=False,
                    value=value,
                    old_value=old_value,
                    error=message,
                    detail=describe_exception(exc),
                )
            )
            log.error(message, node=node_name, attribute=state.plug_name,
                      detail=describe_exception(exc))
            return

        # Audit trail: every successful write is recorded so the Log panel can show
        # what actually changed after the fact (target is the full write path).
        log.info(
            f"{format_value(old_value)} → {format_value(value)}",
            node=target,
        )
        report.items.append(
            ApplyItemResult(
                node_name=node_name,
                channel_label=state.channel.display_label,
                target=target,
                success=True,
                value=value,
                old_value=old_value,
            )
        )

    # ------------------------------------------------------------ low level read/write

    @staticmethod
    def target_for(node_name: str, plug_path: str) -> str:
        """Compose the complete write target: ``full node path.plug long attribute name``.

        ``node_name`` is the full DAG path or the unique DG name, and ``plug_path`` is
        derived from the real plug (including the array index and the compound long
        name), therefore it never writes to a node that merely shares the same name.
        """
        return f"{node_name}.{plug_path}"

    @staticmethod
    def write_value(target: str, value: Any, kind: AttributeKind) -> None:
        """Write one value.

        Everything goes through ``cmds.setAttr``: it was measured to reliably enter the
        Undo queue, and it gives a readable error message for Locked / Connected (the API
        setter only gives "Unexpected Internal Failure").
        """
        from maya import cmds

        if kind is AttributeKind.STRING:
            cmds.setAttr(target, value, type="string")
        else:
            cmds.setAttr(target, value)

    @staticmethod
    def read_value(target: str) -> Any:
        """Read the current value (used only for preview display; returns None on failure)."""
        from maya import cmds

        try:
            return cmds.getAttr(target)
        except (RuntimeError, ValueError):
            return None
