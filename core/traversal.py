"""DAG traversal: expands the selected root nodes into a unique node set.

**Shape nodes must be included** (a key requirement). Empirically confirmed:

* ``cmds.ls(node, shapes=True)`` returns ``[]`` in this Maya version -- unusable;
* ``cmds.listRelatives(node, shapes=True)`` works, but only covers one level;
* ``MItDag(kDepthFirst, kInvalid)`` fully and correctly enumerates Transform /
  Shape / Intermediate Shape and also reports the depth, so it is the single
  traversal implementation used here.

Note: the MItDag filter parameter **cannot** be used as a type filter on its own --
with the ``kMesh`` filter the root Transform is still returned. Type decisions are
always based on ``path.node().hasFn(...)``.

This module reserves an extension point for the Dependency Graph (see
:class:`TraversalScope`), but by **default never** recurses into the DG: the whole
DG can be extremely large, and it would pull in nodes that do not belong to the
current hierarchy.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple

from maya.api import OpenMaya as om2

from utils import maya_utils
from utils.logging_utils import plural


class TraversalScope(enum.Enum):
    """Node search scope.

    The first version implements only the first two; the remaining ones are
    **explicit** extension points, disabled by default and never silently folded
    into the default scope.
    """

    SELECTION_ONLY = "selection_only"
    SELECTION_AND_DESCENDANTS = "selection_and_descendants"
    # Reserved (not implemented):
    # DEPENDENCY_CONNECTIONS = "dependency_connections"
    # HISTORY = "history"
    # REFERENCED = "referenced"


SCOPE_LABELS: Tuple[Tuple[TraversalScope, str], ...] = (
    (TraversalScope.SELECTION_AND_DESCENDANTS, "Selection + all descendants (incl. shapes)"),
    (TraversalScope.SELECTION_ONLY, "Selection only"),
)


@dataclass
class NodeRecord:
    """One node in the traversal result.

    **Important pitfall (measured)**: after a node has been deleted, the old
    ``MObject``'s ``isNull()`` still returns ``False``, and
    ``MFnDependencyNode(mobject).name()`` / ``attributeCount()`` / ``findPlug()``
    keep returning **stale data without raising**. If the old MObject is used
    directly for the pre-Apply re-check, a deleted node "looks perfectly writable"
    and the write then fails.

    Every record therefore stores the node ``uuid``, and every re-check relocates
    the node by UUID through :meth:`resolve_object`:

    * ``cmds.ls(uuid, long=True)`` returns ``[]`` once the node is deleted
      (reliable);
    * a UUID **can still locate the node after it has been renamed** (measured),
      which is more robust than re-checking by name.
    """

    name: str                       # full path for DAG, unique name for DG
    node: om2.MObject
    node_type: str
    uuid: str = ""
    depth: int = 0
    dag_path: Optional[om2.MDagPath] = None
    is_shape: bool = False
    is_intermediate: bool = False
    is_dag: bool = False

    @property
    def display_name(self) -> str:
        """Short name used for display in the UI."""
        if self.dag_path is not None:
            try:
                return self.dag_path.partialPathName()
            except RuntimeError:
                pass
        return self.name.rsplit("|", 1)[-1]

    @property
    def parent_name(self) -> str:
        """Full path of the parent node (empty when there is no parent)."""
        return self.name.rsplit("|", 1)[0] if "|" in self.name else ""

    def current_name(self) -> Optional[str]:
        """The node's current full path name; returns None once the node is deleted.

        The difference from :attr:`name`: the node may have been renamed, in which
        case the new name is returned here.
        """
        if not self.uuid:
            return None if _safe(self.node.isNull, True) else self.name
        return maya_utils.node_by_uuid(self.uuid)

    def is_alive(self) -> bool:
        """Whether the node still exists right now (UUID based, reliable)."""
        return self.current_name() is not None

    def resolve_object(self) -> Optional[om2.MObject]:
        """Re-resolve the **current** MObject from the UUID; None if it was deleted.

        Validation and writes must go through here and must never reuse the old
        MObject captured at construction time.
        """
        current = self.current_name()
        if current is None:
            return None
        return maya_utils.find_node(current)


class DagTraversal:
    """Hierarchy traversal built on MItDag."""

    @staticmethod
    def make_record(node: om2.MObject, depth: int = 0,
                    dag_path: Optional[om2.MDagPath] = None) -> NodeRecord:
        """Build a NodeRecord (fills in the type, the UUID and the intermediate flag)."""
        path = dag_path if dag_path is not None else maya_utils.dag_path_for(node)
        is_dag = node.hasFn(om2.MFn.kDagNode)
        is_shape = node.hasFn(om2.MFn.kShape)
        is_intermediate = False
        if path is not None:
            is_intermediate = bool(
                _safe(lambda: om2.MFnDagNode(path).isIntermediateObject, False)
            )
        return NodeRecord(
            name=maya_utils.qualified_node_name(node),
            node=node,
            node_type=maya_utils.node_type_name(node),
            uuid=maya_utils.node_uuid(node),
            depth=depth,
            dag_path=path,
            is_shape=is_shape,
            is_intermediate=is_intermediate,
            is_dag=is_dag,
        )

    @staticmethod
    def descendant_names(node: om2.MObject) -> Set[str]:
        """Set of the full paths of all DAG descendants of the node (excluding itself)."""
        names: Set[str] = set()
        path = maya_utils.dag_path_for(node)
        if path is None:
            return names
        for _, record in DagTraversal._walk(path):
            if record.name != maya_utils.qualified_node_name(node):
                names.add(record.name)
        return names

    @staticmethod
    def collect(nodes: Sequence[om2.MObject], scope: TraversalScope) -> List[NodeRecord]:
        """Collect nodes by scope and de-duplicate by full path (first occurrence wins)."""
        collected: List[NodeRecord] = []
        seen: Set[str] = set()

        for node in nodes:
            if node is None or _safe(node.isNull, True):
                continue

            if scope is TraversalScope.SELECTION_ONLY:
                records = [DagTraversal.make_record(node)]
            else:
                records = DagTraversal._expand(node)

            for record in records:
                if record.name in seen:
                    continue
                seen.add(record.name)
                collected.append(record)

        return collected

    @staticmethod
    def _expand(node: om2.MObject) -> List[NodeRecord]:
        """A DAG node expands to itself + all descendants; a non-DAG node returns itself.

        Non-DAG nodes (shader / utility, etc.) have no descendants, so they are
        handled explicitly, which avoids a total failure when no MDagPath can be
        obtained.
        """
        path = maya_utils.dag_path_for(node)
        if path is None:
            return [DagTraversal.make_record(node)]
        return [record for _, record in DagTraversal._walk(path)]

    @staticmethod
    def _walk(path: om2.MDagPath) -> List[Tuple[int, NodeRecord]]:
        """Depth-first traversal (including the starting node itself)."""
        results: List[Tuple[int, NodeRecord]] = []
        try:
            iterator = om2.MItDag(om2.MItDag.kDepthFirst, om2.MFn.kInvalid)
            iterator.reset(path.node())
        except RuntimeError:
            return [(-1, DagTraversal.make_record(path.node(), 0, path))]

        while not iterator.isDone():
            try:
                current = iterator.getPath()
                depth = iterator.depth()
            except RuntimeError:
                break
            node = current.node()
            record = DagTraversal.make_record(node, depth, current)
            results.append((depth, record))
            iterator.next()

        if not results:
            results.append((0, DagTraversal.make_record(path.node(), 0, path)))
        return results

    @staticmethod
    def group_by_depth(records: Sequence[NodeRecord]) -> Dict[int, List[NodeRecord]]:
        """Group by depth (for hierarchical display or statistics in the UI)."""
        grouped: Dict[int, List[NodeRecord]] = {}
        for record in records:
            grouped.setdefault(record.depth, []).append(record)
        return grouped


@dataclass
class TraversalSummary:
    """Traversal statistics, used for the UI result summary."""

    total: int = 0
    transforms: int = 0
    shapes: int = 0
    intermediates: int = 0
    dependency_nodes: int = 0
    other_dag: int = 0

    @classmethod
    def from_records(cls, records: Sequence[NodeRecord]) -> "TraversalSummary":
        summary = cls(total=len(records))
        for record in records:
            if record.is_shape:
                summary.shapes += 1
                if record.is_intermediate:
                    summary.intermediates += 1
            elif not record.is_dag:
                summary.dependency_nodes += 1
            elif record.node.hasFn(om2.MFn.kTransform):
                summary.transforms += 1
            else:
                summary.other_dag += 1
        return summary

    def describe(self) -> str:
        """Single-line summary text."""
        parts = [plural(self.total, "node"), plural(self.transforms, "transform"),
                 plural(self.shapes, "shape")]
        if self.intermediates:
            parts.append(f"({plural(self.intermediates, 'intermediate')})")
        if self.dependency_nodes:
            parts.append(plural(self.dependency_nodes, "DG node"))
        return ", ".join(parts)


def _safe(function, default=None):
    """Call a Maya API that may raise."""
    try:
        return function()
    except (RuntimeError, TypeError, ValueError):
        return default
