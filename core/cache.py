"""Scan cache.

**Correctness before excessive caching.** This cache stores only the **pure data** that
the search results use:

* the attribute name list of each node ``(long_name, short_name)``
* the ``AttributeDefinition`` objects already identified

It **never** takes part in write decisions: the Apply phase always re-resolves the plug
and re-validates, therefore even if the cache is stale the worst case is only a briefly
stale search result, and it will never write to the wrong node.

The cache **does not store MObject / MPlug**: those references become invalid once the
node is deleted, whereas plain strings and dataclasses can be held safely long term.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from core.types import AttributeDefinition
from i18n import tr
from utils.logging_utils import plural

NamePair = Tuple[str, str]


@dataclass
class CacheStats:
    """Cache statistics (used for the UI status hint)."""

    nodes: int = 0
    names: int = 0
    definitions: int = 0
    generation: int = 0

    def describe(self) -> str:
        """One-line cache summary for the UI status hint."""
        return tr("cache.describe",
                  nodes=plural(self.nodes, "node"),
                  definitions=plural(self.definitions, "type definition"),
                  generation=self.generation)


class ScanCache:
    """Cache of node attribute names and type definitions."""

    def __init__(self) -> None:
        self._names: Dict[str, Tuple[NamePair, ...]] = {}
        self._definitions: Dict[Tuple[str, str], AttributeDefinition] = {}
        self._generation = 0

    # ---------------------------------------------------------------- invalidation

    @property
    def generation(self) -> int:
        """Current generation; incremented on every invalidation, so the UI can tell
        whether a refresh is needed."""
        return self._generation

    def invalidate(self) -> int:
        """Clear the cache and increment the generation."""
        self._names.clear()
        self._definitions.clear()
        self._generation += 1
        return self._generation

    def invalidate_nodes(self, node_names: Sequence[str]) -> None:
        """Invalidate only the given nodes (used when a node is deleted or its
        attributes change)."""
        for name in node_names:
            self._names.pop(name, None)
            for key in [k for k in self._definitions if k[0] == name]:
                self._definitions.pop(key, None)

    # ---------------------------------------------------------------- attribute names

    def names(self, node_name: str) -> Optional[Tuple[NamePair, ...]]:
        """Get the cached attribute name list; returns None when it is not cached."""
        return self._names.get(node_name)

    def store_names(self, node_name: str, names: Sequence[NamePair]) -> Tuple[NamePair, ...]:
        """Store the attribute name list."""
        stored = tuple(names)
        self._names[node_name] = stored
        return stored

    # ---------------------------------------------------------------- type definitions

    def definition(self, node_name: str, attribute_name: str) -> Optional[AttributeDefinition]:
        """Get the cached attribute definition; returns None when it is not cached."""
        return self._definitions.get((node_name, attribute_name))

    def store_definition(self, node_name: str, definition: AttributeDefinition) -> None:
        """Store the attribute definition."""
        self._definitions[(node_name, definition.name)] = definition

    # ---------------------------------------------------------------- statistics

    def stats(self) -> CacheStats:
        """Current cache size."""
        return CacheStats(
            nodes=len(self._names),
            names=sum(len(pairs) for pairs in self._names.values()),
            definitions=len(self._definitions),
            generation=self._generation,
        )

    def clear_definitions(self) -> None:
        """Clear only the type definitions (the attribute name tables are kept)."""
        self._definitions.clear()
