"""Attribute scan: enumerate node attributes, match by name, identify types.

Performance design (measured: 2100 nodes with about 480,000 attributes, a pure name
scan takes 0.56 s, writing takes only 0.013 s):

1. **Filter by name first, then identify types.** Type identification has to construct
   an MPlug and several MFn* objects, which is far more expensive than reading a name;
   identifying only the attributes that matched brings a typical search down to almost
   free.
2. **The attribute name table goes into the cache.** Changing the search term does not
   require touching the Maya API again.
3. The cache stores pure data only, and the Apply phase always re-resolves (see
   :mod:`core.cache`).

Existence detection strictly follows the measured conclusion: ``findPlug`` raises
``RuntimeError: (kInvalidParameter)`` for an attribute that does not exist, therefore
only ``MFnDependencyNode.attribute()`` (an MObject that returns ``isNull()``) is used to
probe existence.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence, Tuple

from maya.api import OpenMaya as om2

from core.cache import NamePair, ScanCache
from core.traversal import NodeRecord
from core.type_resolver import TypeResolver
from core.types import AttributeDefinition
from utils import maya_utils


@dataclass
class AttributeMatch:
    """A match result for one ``(node, attribute)`` pair."""

    record: NodeRecord
    name: str
    short_name: str
    definition: AttributeDefinition

    @property
    def node_name(self) -> str:
        return self.record.name


class AttributeScanner:
    """Node attribute enumeration and type identification."""

    def __init__(self, cache: Optional[ScanCache] = None) -> None:
        self.cache = cache if cache is not None else ScanCache()

    # ------------------------------------------------------------ attribute name list

    def attribute_names(self, record: NodeRecord) -> Tuple[NamePair, ...]:
        """All attribute names of a node as ``(long, short)``.

        This is a hot path: on a cache hit the Maya API is not touched at all.
        """
        cached = self.cache.names(record.name)
        if cached is not None:
            return cached
        return self.cache.store_names(record.name, self._read_names(record))

    @staticmethod
    def _read_names(record: NodeRecord) -> List[NamePair]:
        """Read attribute names from Maya; a failed read of one attribute does not affect
        the remaining attributes."""
        pairs: List[NamePair] = []
        seen = set()
        try:
            dep = maya_utils.dependency_node(record.node)
            count = dep.attributeCount()
        except (RuntimeError, ValueError):
            return pairs

        for index in range(count):
            try:
                attribute = dep.attribute(index)
                if attribute is None or attribute.isNull():
                    continue
                fat = om2.MFnAttribute(attribute)
                long_name = fat.name
            except (RuntimeError, TypeError, ValueError):
                continue
            if not long_name or long_name in seen:
                continue
            seen.add(long_name)
            try:
                short_name = fat.shortName or long_name
            except (RuntimeError, TypeError, ValueError):
                short_name = long_name
            pairs.append((long_name, short_name))
        return pairs

    # ------------------------------------------------------------ type definition

    def describe(self, record: NodeRecord, name: str) -> Optional[AttributeDefinition]:
        """Identify the real type of the attribute named ``name`` on ``record``.

        Returns None when the attribute does not exist on that node; this is exactly
        where a "missing attribute" gets identified.
        """
        cached = self.cache.definition(record.name, name)
        if cached is not None:
            return cached

        definition = self._resolve(record, name)
        if definition is not None:
            self.cache.store_definition(record.name, definition)
        return definition

    @staticmethod
    def _resolve(record: NodeRecord, name: str) -> Optional[AttributeDefinition]:
        """The actual type resolution: starting from MObject + MPlug."""
        try:
            dep = maya_utils.dependency_node(record.node)
        except (RuntimeError, ValueError):
            return None

        attribute = maya_utils.find_attribute(dep, name)
        if attribute is None:
            return None

        plug = maya_utils.find_plug(dep, attribute)
        return TypeResolver.describe_attribute(attribute, plug)

    # ------------------------------------------------------------ match iteration

    def iter_matches(self, records: Sequence[NodeRecord], matcher) -> Iterator[AttributeMatch]:
        """Iterate all hits according to the name matcher."""
        for record in records:
            for long_name, short_name in self.attribute_names(record):
                if not matcher.matches(long_name, short_name):
                    continue
                definition = self.describe(record, long_name)
                if definition is None:
                    continue
                yield AttributeMatch(
                    record=record,
                    name=long_name,
                    short_name=short_name,
                    definition=definition,
                )

    def scan_all(self, records: Sequence[NodeRecord]) -> List[AttributeMatch]:
        """Scan all attributes (without name filtering), used by the "browse" mode."""
        matches: List[AttributeMatch] = []
        for record in records:
            for long_name, short_name in self.attribute_names(record):
                definition = self.describe(record, long_name)
                if definition is None:
                    continue
                matches.append(
                    AttributeMatch(
                        record=record,
                        name=long_name,
                        short_name=short_name,
                        definition=definition,
                    )
                )
        return matches
