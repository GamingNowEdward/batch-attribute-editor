"""Core facade: composes the modules into a single entry point the UI can use.

The UI accesses Maya **only** through here, so the UI layer never performs
``cmds.setAttr`` / MPlug operations, and Core can be fully tested under mayapy
without Qt.

Typical usage::

    session = BatchAttributeSession()
    session.resolve_selection(TraversalScope.SELECTION_AND_DESCENDANTS)
    result = session.search("visibility")
    group = result.attributes[0]
    channels = session.channels_for(group)
    payload = ValuePayload()
    payload.set(channels[0], False)
    print(session.preview(group, payload).describe())
    session.apply(group, payload)
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from core.attributes import AttributeScanner
from core.batch_setter import BatchSetter, ValuePayload
from core.cache import ScanCache
from core.results import ApplyReport, PreviewReport
from core.search import (
    AggregatedAttribute,
    MatchMode,
    SearchEngine,
    SearchFilters,
    SearchResult,
)
from core.selection import SelectionManager, SelectionResult
from core.traversal import (
    DagTraversal,
    NodeRecord,
    TraversalScope,
    TraversalSummary,
)
from core.type_resolver import build_channels, resolve_channel_plug
from core.types import ChannelSpec
from utils import maya_utils
from utils.logging_utils import plural


@dataclass
class SessionState:
    """Summary of the current session state (for display in the UI status bar)."""

    scope: TraversalScope = TraversalScope.SELECTION_AND_DESCENDANTS
    root_count: int = 0
    node_count: int = 0
    summary: Optional[TraversalSummary] = None
    selection_note: str = ""

    def describe(self) -> str:
        """Status bar text.

        The node count is reported once, by ``TraversalSummary.describe()``; the root
        count comes from ``SelectionResult.describe()``. Reporting them here as well
        produced duplicated text such as
        ``2 nodes (1 roots) · 2 nodes, 2 transforms, 0 shapes``.
        """
        if not self.node_count:
            return self.selection_note or "not selected"

        parts: List[str] = []
        if self.summary is not None:
            parts.append(self.summary.describe())
        else:
            parts.append(plural(self.node_count, "node"))
        if self.selection_note:
            parts.append(self.selection_note)
        elif self.root_count:
            parts.append(plural(self.root_count, "root node"))
        return " · ".join(parts)


class BatchAttributeSession:
    """A single batch attribute editing session."""

    def __init__(self) -> None:
        self.cache = ScanCache()
        self.scanner = AttributeScanner(self.cache)
        self.search_engine = SearchEngine(self.scanner)
        self.setter = BatchSetter()
        self.state = SessionState()

        self.selection: Optional[SelectionResult] = None
        self.records: List[NodeRecord] = []
        self.last_search: Optional[SearchResult] = None
        self._channel_cache: Dict[Tuple, Tuple[ChannelSpec, ...]] = {}

    # ------------------------------------------------------------ Selection and traversal

    def resolve_selection(self, scope: TraversalScope = TraversalScope.SELECTION_AND_DESCENDANTS,
                          nodes: Optional[Sequence[str]] = None,
                          collect: bool = True) -> SelectionResult:
        """Resolve the current selection and collect nodes according to the scope."""
        self.state.scope = scope
        self.selection = SelectionManager.resolve(nodes)
        self.state.root_count = len(self.selection.roots)
        self.state.selection_note = self.selection.describe()

        if collect:
            self.collect_nodes(scope)
        return self.selection

    def collect_nodes(self, scope: Optional[TraversalScope] = None) -> List[NodeRecord]:
        """Expand nodes according to the scope (including Shape / Intermediate)."""
        scope = scope or self.state.scope
        self.state.scope = scope
        roots = [record.node for record in (self.selection.roots if self.selection else [])]
        self.records = DagTraversal.collect(roots, scope)
        self.state.node_count = len(self.records)
        self.state.summary = TraversalSummary.from_records(self.records)
        self._channel_cache.clear()
        return self.records

    # ------------------------------------------------------------ Search

    def search(self, pattern: str = "", filters: Optional[SearchFilters] = None,
               mode: MatchMode = MatchMode.CONTAINS) -> SearchResult:
        """Search by attribute name and aggregate the results."""
        result = self.search_engine.search(self.records, pattern, filters, mode)
        self.last_search = result
        return result

    def search_all(self, filters: Optional[SearchFilters] = None) -> SearchResult:
        """List every attribute (empty pattern)."""
        return self.search("", filters)

    # ------------------------------------------------------------ Channels

    def channels_for(self, group: AggregatedAttribute) -> Tuple[ChannelSpec, ...]:
        """The **channel union** of an aggregated item.

        Different nodes may have different sets of array indices (``input[0]``
        exists only on some nodes), so the channels are unioned; the actual write
        re-validates node by node, and the missing ones are skipped.
        """
        cached = self._channel_cache.get(group.signature)
        if cached is not None:
            return cached

        collected: Dict[Tuple, ChannelSpec] = {}
        for record in group.records:
            plug = self._plug_for(record, group.name)
            if plug is None:
                continue
            for channel in build_channels(plug, group.definition):
                collected.setdefault(channel.key, channel)

        channels = tuple(
            sorted(
                collected.values(),
                key=lambda item: (
                    0 if item.element_index is None else 1,
                    item.element_index if item.element_index is not None else 0,
                    item.child_index if item.child_index is not None else -1,
                ),
            )
        )
        self._channel_cache[group.signature] = channels
        return channels

    def sample_values(self, group: AggregatedAttribute,
                      channels: Sequence[ChannelSpec]) -> Dict[Tuple, object]:
        """Read the current value from the first usable node, for UI pre-fill.

        Used for **display** only and never part of the write -- the write always
        uses the value the user entered.
        """
        samples: Dict[Tuple, object] = {}
        from maya import cmds

        for record in group.records:
            plug = self._plug_for(record, group.name)
            if plug is None:
                continue
            for channel in channels:
                channel_plug = resolve_channel_plug(plug, channel)
                if channel_plug is None:
                    continue
                try:
                    target = self.setter.target_for(
                        record.name, maya_utils.plug_attribute_path(channel_plug)
                    )
                    samples[channel.key] = cmds.getAttr(target)
                except (RuntimeError, ValueError):
                    continue
            if samples:
                break
        return samples

    # ------------------------------------------------------------ Preview and apply

    def preview(self, group: AggregatedAttribute, payload: ValuePayload) -> PreviewReport:
        """Build the modification preview.

        The preview covers **every node inside the scan scope**, so the user can see
        "which nodes do not have this attribute at all" (requirement section 19).
        Apply only walks the nodes that actually have the attribute.
        """
        return self.setter.preview(group, payload, all_records=self.records)

    def apply(self, group: AggregatedAttribute, payload: ValuePayload) -> ApplyReport:
        """Apply the batch edit (one single Undo for the whole batch)."""
        report = self.setter.apply(group, payload)
        # A write may change locked/connected state, so discard the validation
        # cache to keep the next preview accurate.
        group.invalidate_validation()
        return report

    # ------------------------------------------------------------ Refresh

    def refresh(self) -> SessionState:
        """Clear the caches and resolve the selection again."""
        self.cache.invalidate()
        self._channel_cache.clear()
        self.resolve_selection(self.state.scope)
        return self.state

    def invalidate_cache(self) -> None:
        """Clear only the scan cache (triggered by scene events)."""
        self.cache.invalidate()
        self._channel_cache.clear()

    def cache_note(self) -> str:
        """Cache status note."""
        return self.cache.stats().describe()

    # ------------------------------------------------------------ Internal

    @staticmethod
    def _plug_for(record: NodeRecord, attribute_name: str):
        """Get the plug of an attribute on a node; returns None if absent or unusable.

        The node is re-resolved through its UUID so that a possibly stale MObject is
        never used.
        """
        mobject = record.resolve_object()
        if mobject is None:
            return None
        try:
            dep = maya_utils.dependency_node(mobject)
        except (RuntimeError, ValueError):
            return None
        attribute = maya_utils.find_attribute(dep, attribute_name)
        if attribute is None:
            return None
        return maya_utils.find_plug(dep, attribute)
