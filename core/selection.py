"""Selection management: resolve Maya's current selection into a de-duplicated set of unique roots.

Why de-duplication is needed (requirement section 4): the user may select ``Group`` and the
``MeshA`` inside ``Group`` at the same time; ``MeshA`` is then already a descendant of ``Group``
and must never be processed twice.

De-duplication algorithm: for every DAG root, compute the set of full paths of its descendants;
if one root's full path appears in **another** root's descendant set, that root is covered and is
removed. This uses the real hierarchy instead of string comparison, which avoids false prefix
matches such as ``|A|BC`` versus ``|A|B``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Set, Tuple

from core.traversal import DagTraversal, NodeRecord
from i18n import tr
from utils import maya_utils
from utils.logging_utils import plural


@dataclass
class SelectionResult:
    """Selection resolution result."""

    roots: List[NodeRecord] = field(default_factory=list)
    ignored: List[Tuple[str, str]] = field(default_factory=list)
    covered: List[str] = field(default_factory=list)
    requested: int = 0

    @property
    def is_empty(self) -> bool:
        return not self.roots

    def describe(self) -> str:
        """One-line summary for the UI status bar."""
        if self.is_empty:
            return tr("selection.empty")
        text = plural(len(self.roots), "root node")
        if self.covered:
            text += tr("selection.covered", count=len(self.covered))
        if self.ignored:
            text += tr("selection.ignored", count=len(self.ignored))
        return text


class SelectionManager:
    """Selection resolution and de-duplication."""

    @staticmethod
    def current_selection() -> List[str]:
        """Full path names of the current selection.

        Note that ``cmds.ls(sl=True)`` only returns Transforms (Shapes never appear in the
        selection result); this is fine, since :class:`DagTraversal` adds Shapes as descendants.
        """
        from maya import cmds

        try:
            return list(cmds.ls(selection=True, long=True) or [])
        except RuntimeError:
            return []

    @classmethod
    def resolve(cls, nodes: Optional[Sequence[str]] = None) -> SelectionResult:
        """Resolve a node name list (the current selection by default), returning unique roots."""
        requested = list(nodes) if nodes is not None else cls.current_selection()
        result = SelectionResult(requested=len(requested))

        records: List[NodeRecord] = []
        for name in requested:
            node = maya_utils.find_node(name)
            if node is None:
                result.ignored.append((name, "Node does not exist or the name is ambiguous"))
                continue
            records.append(DagTraversal.make_record(node))

        result.roots = cls.dedupe(records, result.covered)
        return result

    @staticmethod
    def dedupe(records: Sequence[NodeRecord], covered_out: Optional[List[str]] = None
               ) -> List[NodeRecord]:
        """Drop roots covered by another root node, keeping the input order."""
        descendant_cache: dict = {}
        for record in records:
            if record.dag_path is not None:
                descendant_cache[record.name] = DagTraversal.descendant_names(record.node)

        kept: List[NodeRecord] = []
        for record in records:
            covered = False
            for other in records:
                if other is record:
                    continue
                descendants = descendant_cache.get(other.name)
                if descendants and record.name in descendants:
                    covered = True
                    break
            if covered:
                if covered_out is not None:
                    covered_out.append(record.name)
            else:
                kept.append(record)
        return kept

    @staticmethod
    def unique_node_names(records: Sequence[NodeRecord]) -> List[str]:
        """Unique full path names for a list of records."""
        seen: Set[str] = set()
        names: List[str] = []
        for record in records:
            if record.name in seen:
                continue
            seen.add(record.name)
            names.append(record.name)
        return names
