"""Core layer: completely independent of Qt, testable standalone under mayapy.

Layering is described in docs/ARCHITECTURE.md section 2::

    selection → traversal → attributes/type_resolver → compatibility
    → search → batch_setter(+undo) → results

The UI reaches Core only through :class:`core.session.BatchAttributeSession`.
"""

from __future__ import annotations

from core.batch_setter import (
    BatchSetter,
    ValueCoercionError,
    ValuePayload,
    coerce_value,
)
from core.cache import ScanCache
from core.compatibility import (
    BLOCKING_STATUSES,
    ChannelState,
    CompatibilityValidator,
    NodeValidation,
    ValidationStatus,
    ValidationSummary,
    status_label,
)
from core.results import (
    ApplyItemResult,
    ApplyReport,
    ChannelChange,
    PreviewItem,
    PreviewReport,
)
from core.search import (
    AggregatedAttribute,
    MatchMode,
    NameMatcher,
    SearchEngine,
    SearchFilters,
    SearchResult,
)
from core.selection import SelectionManager, SelectionResult
from core.session import BatchAttributeSession, SessionState
from core.traversal import (
    SCOPE_LABELS,
    DagTraversal,
    NodeRecord,
    TraversalScope,
    TraversalSummary,
)
from core.type_resolver import (
    TypeResolver,
    build_channels,
    resolve_channel_plug,
)
from core.types import (
    AttributeDefinition,
    AttributeKind,
    ChannelSpec,
    EditorKind,
    editor_kind_for,
)
from core.undo import UndoManager

__all__ = [
    "AggregatedAttribute",
    "ApplyItemResult",
    "ApplyReport",
    "AttributeDefinition",
    "AttributeKind",
    "BLOCKING_STATUSES",
    "BatchAttributeSession",
    "BatchSetter",
    "ChannelChange",
    "ChannelSpec",
    "ChannelState",
    "CompatibilityValidator",
    "DagTraversal",
    "EditorKind",
    "MatchMode",
    "NameMatcher",
    "NodeRecord",
    "NodeValidation",
    "PreviewItem",
    "PreviewReport",
    "SCOPE_LABELS",
    "ScanCache",
    "SearchEngine",
    "SearchFilters",
    "SearchResult",
    "SelectionManager",
    "SelectionResult",
    "SessionState",
    "TraversalScope",
    "TraversalSummary",
    "TypeResolver",
    "UndoManager",
    "ValidationStatus",
    "ValidationSummary",
    "ValueCoercionError",
    "ValuePayload",
    "build_channels",
    "coerce_value",
    "editor_kind_for",
    "resolve_channel_plug",
    "status_label",
]
