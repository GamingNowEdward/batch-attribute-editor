"""Compatibility validation: decides "whether this attribute can actually be changed on this node".

Validation order (corresponds to requirement section 16):

    node exists → attribute exists → readable → writable → type compatible
    → Locked / Connected / structural match for each channel

The default policy is **non-destructive**: Locked and Connected are always skipped with a reason,
never auto-unlocked, never disconnected, array elements are never created, and no implicit type
conversion is ever performed.

Empirical basis (Maya 2024 / API 2.0):

* ``plug.isLocked`` / ``plug.isConnected`` / ``plug.isDestination`` are **properties**.
* ``plug.isFreeToChange()`` is a **method**, returning ``0=kFreeToChange``,
  ``1=kNotFreeToChange``, ``2=kChildrenNotFreeToChange``.
* **A compound parent plug still has ``isConnected`` False when only child plugs are connected**,
  so ``numConnectedChildren()`` / ``isFreeToChange()`` must be checked as well, otherwise the case
  is missed and the write fails.
* ``findPlug("a non-existent attribute")`` raises an exception, so existence can only be tested
  with ``dep.attribute()`` + ``MObject.isNull()``.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from maya.api import OpenMaya as om2

from core.traversal import NodeRecord
from core.type_resolver import (
    TypeResolver,
    build_channels,
    resolve_channel_plug,
)
from core.types import AttributeDefinition, ChannelSpec
from utils import maya_utils


class ValidationStatus(enum.Enum):
    """Status of a single validation result."""

    OK = "ok"
    NODE_MISSING = "node_missing"
    MISSING = "missing"
    TYPE_MISMATCH = "type_mismatch"
    NOT_READABLE = "not_readable"
    NOT_WRITABLE = "not_writable"
    LOCKED = "locked"
    CONNECTED = "connected"
    CHANNEL_MISSING = "channel_missing"
    UNSUPPORTED = "unsupported"


#: User-facing status descriptions
STATUS_LABELS: Dict[ValidationStatus, str] = {
    ValidationStatus.OK: "Writable",
    ValidationStatus.NODE_MISSING: "Node no longer exists",
    ValidationStatus.MISSING: "Attribute missing",
    ValidationStatus.TYPE_MISMATCH: "Type mismatch",
    ValidationStatus.NOT_READABLE: "Not readable",
    ValidationStatus.NOT_WRITABLE: "Not writable",
    ValidationStatus.LOCKED: "Locked",
    ValidationStatus.CONNECTED: "Connected",
    ValidationStatus.CHANNEL_MISSING: "Array element missing",
    ValidationStatus.UNSUPPORTED: "Unsupported type",
}

#: Statuses that must be counted as "skipped" (everything other than OK)
BLOCKING_STATUSES = tuple(status for status in ValidationStatus if status is not ValidationStatus.OK)


def status_label(status: ValidationStatus) -> str:
    """User-facing text for a status."""
    return STATUS_LABELS.get(status, status.value)


@dataclass
class ChannelState:
    """Writability state of a single channel."""

    channel: ChannelSpec
    status: ValidationStatus = ValidationStatus.OK
    reason: str = ""
    plug_name: str = ""

    @property
    def writable(self) -> bool:
        return self.status is ValidationStatus.OK


@dataclass
class NodeValidation:
    """Complete validation result of one attribute on one node."""

    record: NodeRecord
    attribute_name: str
    definition: Optional[AttributeDefinition] = None
    statuses: Tuple[ValidationStatus, ...] = ()
    reasons: Tuple[str, ...] = ()
    channel_states: Tuple[ChannelState, ...] = ()
    current_name: str = ""

    @property
    def node_name(self) -> str:
        """Stable identity (name captured during traversal), for reporting and de-duplication."""
        return self.record.name

    @property
    def target_base(self) -> str:
        """Node part of the write target: prefer the **current name at re-check time**
        (the node may have been renamed)."""
        return self.current_name or self.record.name

    @property
    def display_name(self) -> str:
        return self.record.display_name

    @property
    def is_ok(self) -> bool:
        """Whether all attribute-level validations passed."""
        return not self.statuses

    @property
    def writable_channels(self) -> Tuple[ChannelState, ...]:
        return tuple(state for state in self.channel_states if state.writable)

    @property
    def blocked_channels(self) -> Tuple[ChannelState, ...]:
        return tuple(state for state in self.channel_states if not state.writable)

    @property
    def has_writable_channel(self) -> bool:
        """Whether at least one writable channel exists - decides if the node enters the
        "will modify" list."""
        return bool(self.writable_channels)

    @property
    def fully_writable(self) -> bool:
        """All channels are writable."""
        return bool(self.channel_states) and not self.blocked_channels

    def skip_reason(self) -> str:
        """Skip reason (user-facing)."""
        parts: List[str] = [status_label(status) for status in self.statuses]
        for state in self.blocked_channels:
            if state.reason and state.reason not in parts:
                parts.append(state.reason)
        return ", ".join(dict.fromkeys(parts)) if parts else ""

    def primary_status(self) -> ValidationStatus:
        """Most representative status (used for list coloring)."""
        if self.statuses:
            return self.statuses[0]
        for state in self.blocked_channels:
            return state.status
        return ValidationStatus.OK


@dataclass
class ValidationSummary:
    """Statistics over a set of validation results (used by Details and Preview)."""

    total: int = 0
    writable: int = 0
    partially_writable: int = 0
    skipped: int = 0
    counts: Dict[ValidationStatus, int] = field(default_factory=dict)

    @property
    def fully_writable(self) -> int:
        return max(self.writable - self.partially_writable, 0)

    def add(self, status: ValidationStatus) -> None:
        self.counts[status] = self.counts.get(status, 0) + 1

    def count(self, status: ValidationStatus) -> int:
        return self.counts.get(status, 0)

    def describe(self) -> str:
        """Summary text."""
        parts = [f"Matched {self.total}", f"Writable {self.writable}", f"Skipped {self.skipped}"]
        for status in (
            ValidationStatus.LOCKED,
            ValidationStatus.CONNECTED,
            ValidationStatus.MISSING,
            ValidationStatus.TYPE_MISMATCH,
            ValidationStatus.NOT_WRITABLE,
            ValidationStatus.CHANNEL_MISSING,
        ):
            value = self.count(status)
            if value:
                parts.append(f"{status_label(status)} {value}")
        return ", ".join(parts)


class CompatibilityValidator:
    """Attribute writability validation."""

    @classmethod
    def validate(cls, record: NodeRecord, attribute_name: str,
                 expected: Optional[AttributeDefinition] = None,
                 channels: Sequence[ChannelSpec] = ()) -> NodeValidation:
        """Validate the writability of an attribute on a node.

        :param expected: the type definition chosen by the user; used to detect nodes where the
            "same name has a different type".
        :param channels: the channels to write; when empty, only attribute-level validation runs.

        Note: the node is **re-resolved by UUID**, never using the old MObject captured during
        traversal - empirically an old MObject returns stale data after the node was deleted
        without raising an error.
        """
        statuses: List[ValidationStatus] = []
        reasons: List[str] = []

        current_name = record.current_name()
        if current_name is None:
            return NodeValidation(
                record=record,
                attribute_name=attribute_name,
                statuses=(ValidationStatus.NODE_MISSING,),
                reasons=(status_label(ValidationStatus.NODE_MISSING),),
            )

        mobject = record.resolve_object()
        if mobject is None:
            return NodeValidation(
                record=record,
                attribute_name=attribute_name,
                statuses=(ValidationStatus.NODE_MISSING,),
                reasons=(status_label(ValidationStatus.NODE_MISSING),),
            )

        try:
            dep = maya_utils.dependency_node(mobject)
        except (RuntimeError, ValueError):
            return NodeValidation(
                record=record,
                attribute_name=attribute_name,
                current_name=current_name,
                statuses=(ValidationStatus.NODE_MISSING,),
                reasons=(status_label(ValidationStatus.NODE_MISSING),),
            )

        attribute = maya_utils.find_attribute(dep, attribute_name)
        if attribute is None:
            # Requirement section 19: the attribute exists only on some nodes, the rest must be
            # reported as missing.
            return NodeValidation(
                record=record,
                attribute_name=attribute_name,
                current_name=current_name,
                statuses=(ValidationStatus.MISSING,),
                reasons=(status_label(ValidationStatus.MISSING),),
            )

        plug = maya_utils.find_plug(dep, attribute)
        definition = TypeResolver.describe_attribute(attribute, plug)

        if expected is not None and definition.signature != expected.signature:
            return NodeValidation(
                record=record,
                attribute_name=attribute_name,
                definition=definition,
                current_name=current_name,
                statuses=(ValidationStatus.TYPE_MISMATCH,),
                reasons=(f"{status_label(ValidationStatus.TYPE_MISMATCH)}"
                         f" (node has {definition.type_label})",),
            )

        if not definition.is_readable:
            statuses.append(ValidationStatus.NOT_READABLE)
            reasons.append(status_label(ValidationStatus.NOT_READABLE))
        if not definition.is_writable:
            statuses.append(ValidationStatus.NOT_WRITABLE)
            reasons.append(status_label(ValidationStatus.NOT_WRITABLE))
        if not definition.supports_editing:
            statuses.append(ValidationStatus.UNSUPPORTED)
            reasons.append(status_label(ValidationStatus.UNSUPPORTED))

        channel_states = cls._validate_channels(plug, definition, channels)

        return NodeValidation(
            record=record,
            attribute_name=attribute_name,
            definition=definition,
            statuses=tuple(statuses),
            reasons=tuple(reasons),
            channel_states=channel_states,
            current_name=current_name,
        )

    # ------------------------------------------------------------ Channel level

    @classmethod
    def _validate_channels(cls, plug: Optional[om2.MPlug], definition: AttributeDefinition,
                           channels: Sequence[ChannelSpec]) -> Tuple[ChannelState, ...]:
        """Check structure, Locked and Connected for each channel.

        When ``channels`` is empty, all channels are **automatically** derived from the plug
        structure. This matters: if the caller forgets to pass channels, the attribute would be
        skipped as a whole for "having no writable channel", and the batch edit would silently
        fail. Automatic derivation makes this API impossible to misuse that way.
        """
        if not channels and plug is not None and not maya_utils.plug_is_null(plug):
            channels = build_channels(plug, definition)

        states: List[ChannelState] = []
        existing_indices: Optional[List[int]] = None
        if plug is not None and not maya_utils.plug_is_null(plug) and plug.isArray:
            existing_indices = maya_utils.existing_element_indices(plug)

        for channel in channels:
            # Array elements must **already exist** - version 1 does not create array elements.
            if channel.element_index is not None and existing_indices is not None:
                if channel.element_index not in existing_indices:
                    states.append(
                        ChannelState(channel=channel, status=ValidationStatus.CHANNEL_MISSING,
                                     reason=f"[{channel.element_index}] {status_label(ValidationStatus.CHANNEL_MISSING)}")
                    )
                    continue

            channel_plug = resolve_channel_plug(plug, channel)
            if channel_plug is None:
                states.append(
                    ChannelState(channel=channel, status=ValidationStatus.CHANNEL_MISSING,
                                 reason=status_label(ValidationStatus.CHANNEL_MISSING))
                )
                continue

            plug_name = maya_utils.plug_attribute_path(channel_plug)
            status, reason = cls._plug_state(channel_plug)
            states.append(ChannelState(channel=channel, status=status, reason=reason, plug_name=plug_name))
        return tuple(states)

    @staticmethod
    def _plug_state(plug: om2.MPlug) -> Tuple[ValidationStatus, str]:
        """Locked/connected state of a single plug.

        Only attributes with an **input connection** (destination) are not writable: an attribute
        that is the connection **source** is still writable, and the write propagates downstream
        normally.

        Measured: ``plug.isConnected`` is **True for both** source and destination (after
        ``cmds.connectAttr(src, dst)`` both ends have ``isConnected`` true), so ``isConnected``
        must never be used as the "not writable" criterion - ``isDestination`` is the one to check.

        Decision order: check the explicit ``isLocked`` first, then ``isDestination``, and only
        then fall back to ``isFreeToChange()`` (it covers both locks and connected child plugs,
        returning ``kNotFreeToChange(1)`` / ``kChildrenNotFreeToChange(2)``).
        """
        try:
            if bool(plug.isLocked):
                return ValidationStatus.LOCKED, status_label(ValidationStatus.LOCKED)
        except RuntimeError:
            pass

        try:
            if bool(plug.isDestination):
                return ValidationStatus.CONNECTED, status_label(ValidationStatus.CONNECTED)
        except RuntimeError:
            pass

        try:
            if plug.isFreeToChange() != om2.MPlug.kFreeToChange:
                return ValidationStatus.CONNECTED, status_label(ValidationStatus.CONNECTED)
        except (RuntimeError, TypeError):
            pass

        return ValidationStatus.OK, ""

    # ------------------------------------------------------------ Summary

    @staticmethod
    def summarize(validations: Sequence[NodeValidation]) -> ValidationSummary:
        """Compute statistics over a set of validation results."""
        summary = ValidationSummary(total=len(validations))
        for validation in validations:
            if validation.has_writable_channel:
                summary.writable += 1
                if validation.blocked_channels:
                    summary.partially_writable += 1
            else:
                summary.skipped += 1
            for status in validation.statuses:
                summary.add(status)
            for state in validation.blocked_channels:
                if state.status not in validation.statuses:
                    summary.add(state.status)
        return summary
