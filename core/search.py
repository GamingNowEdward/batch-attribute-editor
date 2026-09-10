"""Attribute search and result aggregation.

The aggregation key is ``(attribute name, type, type label, whether multi)`` (see
``AttributeDefinition.signature``), so requirement section 20's "same name, different type
attributes" are naturally split into separate result rows:

    someAttr  Float     nodeA
    someAttr  Integer   nodeB
    someAttr  Boolean   nodeC

Once the user picks one of those rows, only type-compatible nodes are modified and the rest go into
the skip report - no implicit type conversion is ever performed.

Validation (Locked / Connected / Missing) runs **on demand**: the search result first reports
"attribute name + type + node count", and the full validation of a row's nodes only happens after
the user selects that row, so the initial search stays fast even with 10000+ nodes.
"""

from __future__ import annotations

import enum
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from core.attributes import AttributeScanner
from core.compatibility import (
    CompatibilityValidator,
    NodeValidation,
    ValidationStatus,
    ValidationSummary,
)
from core.traversal import NodeRecord
from core.types import AttributeDefinition, AttributeKind
from utils.logging_utils import plural


class MatchMode(enum.Enum):
    """Attribute name matching mode."""

    CONTAINS = "contains"
    EXACT = "exact"
    PREFIX = "prefix"
    FUZZY = "fuzzy"


MATCH_MODE_LABELS: Tuple[Tuple[MatchMode, str], ...] = (
    (MatchMode.CONTAINS, "Contains"),
    (MatchMode.EXACT, "Exact"),
    (MatchMode.PREFIX, "Prefix"),
    (MatchMode.FUZZY, "Fuzzy"),
)


class NameMatcher:
    """Attribute name matcher: case-insensitive, matches both Long Name and Short Name."""

    def __init__(self, pattern: str, mode: MatchMode = MatchMode.CONTAINS) -> None:
        self.pattern = (pattern or "").strip()
        self.mode = mode
        self._needle = self.pattern.lower()

    @property
    def is_empty(self) -> bool:
        """An empty pattern matches every attribute."""
        return not self._needle

    def matches(self, long_name: str, short_name: str = "") -> bool:
        """Return whether the attribute name is a hit."""
        if self.is_empty:
            return True
        candidates = {long_name.lower()}
        if short_name:
            candidates.add(short_name.lower())

        if self.mode is MatchMode.EXACT:
            return self._needle in candidates
        if self.mode is MatchMode.PREFIX:
            return any(candidate.startswith(self._needle) for candidate in candidates)
        if self.mode is MatchMode.FUZZY:
            return any(_is_subsequence(self._needle, candidate) for candidate in candidates)
        return any(self._needle in candidate for candidate in candidates)


def _is_subsequence(needle: str, haystack: str) -> bool:
    """Whether needle is a subsequence of haystack (fuzzy matching)."""
    iterator = iter(haystack)
    return all(char in iterator for char in needle)


@dataclass
class SearchFilters:
    """Search filters (requirement section 30, an enhancement feature)."""

    only_writable: bool = False
    only_keyable: bool = False
    only_user_defined: bool = False
    hide_unsupported: bool = True
    hide_compound_children: bool = False
    hide_locked: bool = False
    hide_connected: bool = False
    kinds: Tuple[AttributeKind, ...] = ()

    @property
    def needs_validation(self) -> bool:
        """Whether write-state validation is needed for the filters (expensive, only when
        checked)."""
        return self.hide_locked or self.hide_connected

    def accepts_definition(self, definition: AttributeDefinition) -> bool:
        """Definition-level filtering (cheap)."""
        if self.only_writable and not definition.is_writable:
            return False
        if self.only_keyable and not (definition.is_keyable or definition.is_channel_box):
            # channelBox attributes are not "keyable" in the strict Maya sense but
            # can be keyframed from the Channel Box (e.g. Arnold's aiExposure).
            return False
        if self.only_user_defined and not definition.is_dynamic:
            return False
        if self.hide_unsupported and not definition.supports_editing:
            return False
        if self.hide_compound_children and definition.is_compound_child:
            return False
        if self.kinds and definition.kind not in self.kinds:
            return False
        return True


@dataclass
class AggregatedAttribute:
    """One row of the search result: a ``(attribute name, type)`` group."""

    name: str
    short_name: str
    definition: AttributeDefinition
    records: List[NodeRecord] = field(default_factory=list)
    other_types: Dict[str, int] = field(default_factory=dict)
    _validations: Optional[List[NodeValidation]] = None

    @property
    def signature(self) -> Tuple[str, str, str, bool]:
        return self.definition.signature

    @property
    def type_label(self) -> str:
        return self.definition.type_label

    @property
    def node_count(self) -> int:
        return len(self.records)

    @property
    def display_name(self) -> str:
        """``visibility (v)`` form, showing the long name and the short name together."""
        if self.short_name and self.short_name != self.name:
            return f"{self.name} ({self.short_name})"
        return self.name

    @property
    def other_type_total(self) -> int:
        """Total number of nodes with the same name but a different type (for the hint
        "N other nodes have a different type")."""
        return sum(self.other_types.values())

    def validate(self, force: bool = False) -> List[NodeValidation]:
        """Run full validation over all nodes of this group (the result is cached)."""
        if self._validations is not None and not force:
            return self._validations
        validations: List[NodeValidation] = []
        for record in self.records:
            validations.append(
                CompatibilityValidator.validate(record, self.name, self.definition)
            )
        self._validations = validations
        return validations

    def summary(self, force: bool = False) -> ValidationSummary:
        """Validation statistics (writable / skipped / counts per reason)."""
        return CompatibilityValidator.summarize(self.validate(force=force))

    def writable_records(self, force: bool = False) -> List[NodeValidation]:
        """Return only the validation results of nodes that have a writable channel."""
        return [item for item in self.validate(force=force) if item.has_writable_channel]

    def invalidate_validation(self) -> None:
        """Drop the validation cache (called after Apply or after a scene change)."""
        self._validations = None


@dataclass
class SearchResult:
    """Complete result of one search."""

    pattern: str = ""
    attributes: List[AggregatedAttribute] = field(default_factory=list)
    scanned_nodes: int = 0
    matched_occurrences: int = 0
    elapsed: float = 0.0
    cache_generation: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.attributes

    def describe(self) -> str:
        """Status bar summary."""
        total_nodes = sum(item.node_count for item in self.attributes)
        return (f"Matched {plural(len(self.attributes), 'attribute')} / "
                f"{plural(total_nodes, 'attribute instance')}"
                f" (scanned {plural(self.scanned_nodes, 'node')}, {self.elapsed * 1000:.0f} ms)")


class SearchEngine:
    """Attribute search: scan + match + aggregate."""

    def __init__(self, scanner: Optional[AttributeScanner] = None) -> None:
        self.scanner = scanner if scanner is not None else AttributeScanner()

    def search(self, records: Sequence[NodeRecord], pattern: str = "",
               filters: Optional[SearchFilters] = None,
               mode: MatchMode = MatchMode.CONTAINS) -> SearchResult:
        """Search attributes as requested."""
        filters = filters if filters is not None else SearchFilters()
        matcher = NameMatcher(pattern, mode)
        started = time.perf_counter()

        groups: Dict[Tuple, AggregatedAttribute] = {}
        type_counter: Dict[str, Dict[str, int]] = {}
        matched = 0

        for match in self.scanner.iter_matches(records, matcher):
            definition = match.definition
            if not filters.accepts_definition(definition):
                continue
            matched += 1
            type_counter.setdefault(match.name, {})
            type_counter[match.name][definition.type_label] = (
                type_counter[match.name].get(definition.type_label, 0) + 1
            )

            group = groups.get(definition.signature)
            if group is None:
                group = AggregatedAttribute(
                    name=match.name,
                    short_name=match.short_name,
                    definition=definition,
                )
                groups[definition.signature] = group
            group.records.append(match.record)

        attributes = list(groups.values())
        for group in attributes:
            others = dict(type_counter.get(group.name, {}))
            others.pop(group.definition.type_label, None)
            group.other_types = others

        if filters.needs_validation:
            attributes = self._apply_validation_filters(attributes, filters)

        attributes.sort(key=lambda item: (-item.node_count, item.name.lower()))

        return SearchResult(
            pattern=pattern,
            attributes=attributes,
            scanned_nodes=len(records),
            matched_occurrences=matched,
            elapsed=time.perf_counter() - started,
            cache_generation=self.scanner.cache.generation,
        )

    @staticmethod
    def _apply_validation_filters(attributes: Sequence[AggregatedAttribute],
                                  filters: SearchFilters) -> List[AggregatedAttribute]:
        """Filter groups by Locked / Connected (needs full validation, only runs when checked)."""
        kept: List[AggregatedAttribute] = []
        for group in attributes:
            validations = group.validate()
            if filters.hide_locked:
                if all(
                    ValidationStatus.LOCKED in item.statuses
                    or any(state.status is ValidationStatus.LOCKED for state in item.blocked_channels)
                    for item in validations
                ):
                    continue
            if filters.hide_connected:
                if all(
                    ValidationStatus.CONNECTED in item.statuses
                    or any(state.status is ValidationStatus.CONNECTED for state in item.blocked_channels)
                    for item in validations
                ):
                    continue
            kept.append(group)
        return kept
