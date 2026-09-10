"""Low-level Maya wrappers: node resolution, plug name derivation.

This is where "how to turn an MPlug into a reliable write target string" is
handled centrally. Measured conclusions (Maya 2024 / API 2.0):

* ``MPlug.name()`` returns authoritative names such as ``CubeA.translateX`` /
  ``CubeA.warr[3]``, with the attribute part carrying the correct index, but the
  node part is the **short name**, which is ambiguous when names collide.
* ``MPlug.partialName(includeNodeName, includeNonMandatoryIndices,
  includeInstancedIndices, useAlias, useFullAttributePath, useLongNames)``
  can give you the "long attribute name without the node name".
* Therefore the write target is uniformly built as
  ``fullPathName + "." + long attribute name``, which avoids short-name
  ambiguity and also avoids guessing structures like translateX / warr[3] by
  string concatenation.
"""

from __future__ import annotations

from typing import Iterator, List, Optional, Sequence

from maya.api import OpenMaya as om2

# The 6-argument form of MPlug.partialName: long name only, no node name, and
# include the necessary indices.
_PARTIAL_LONG = (False, False, False, False, False, True)


def get_selection_list(nodes: Sequence[str]) -> om2.MSelectionList:
    """Build an MSelectionList, automatically skipping node names that no longer exist."""
    selection = om2.MSelectionList()
    for node in nodes:
        try:
            selection.add(node)
        except (RuntimeError, ValueError):
            continue
    return selection


def find_node(name: str) -> Optional[om2.MObject]:
    """Get an MObject by name; return None when it does not exist (does not raise)."""
    try:
        selection = om2.MSelectionList()
        selection.add(name)
    except (RuntimeError, ValueError):
        return None
    if selection.length() == 0:
        return None
    return selection.getDependNode(0)


def find_dag_path(name: str) -> Optional[om2.MDagPath]:
    """Get an MDagPath by name; return None for non-DAG nodes or when it does not exist."""
    try:
        selection = om2.MSelectionList()
        selection.add(name)
    except (RuntimeError, ValueError):
        return None
    if selection.length() == 0:
        return None
    try:
        return selection.getDagPath(0)
    except (RuntimeError, TypeError):
        return None


def dependency_node(node: om2.MObject) -> om2.MFnDependencyNode:
    """Construct an MFnDependencyNode."""
    return om2.MFnDependencyNode(node)


def node_display_name(node: om2.MObject) -> str:
    """Node name (unique name, without the DAG path)."""
    return om2.MFnDependencyNode(node).name()


def node_type_name(node: om2.MObject) -> str:
    """Node type name, e.g. transform / mesh / lambert."""
    return om2.MFnDependencyNode(node).typeName


def node_uuid(node: om2.MObject) -> str:
    """The node's UUID string.

    Measured: in API 2.0, ``MFnDependencyNode.uuid()`` returns an ``MUuid``
    **object**, not a string; handing it directly to ``cmds.ls()`` will not
    resolve it as a UUID.
    It must be converted to a string before it can be used for a liveness re-check.
    """
    try:
        value = om2.MFnDependencyNode(node).uuid()
    except (RuntimeError, TypeError, ValueError):
        return ""
    as_string = getattr(value, "asString", None)
    if callable(as_string):
        try:
            return str(as_string())
        except (RuntimeError, TypeError):
            pass
    return str(value)


def node_by_uuid(uuid_text: str) -> Optional[str]:
    """Look up the current full path of a node by UUID; None when it does not exist.

    Measured: after a node is deleted, ``cmds.ls(uuid, long=True)`` returns
    ``[]`` (reliable); after the node is **renamed** it can still be located (so
    this is more robust than re-checking by name).
    Note that the form ``cmds.ls(uuid_string, long=True)`` must be used.
    """
    if not uuid_text:
        return None
    from maya import cmds

    try:
        found = cmds.ls(uuid_text, long=True) or []
    except (RuntimeError, TypeError):
        return None
    return found[0] if found else None


def is_dag_node(node: om2.MObject) -> bool:
    """Whether the node is a DAG node (Transform / Shape, etc.)."""
    return node.hasFn(om2.MFn.kDagNode)


def is_shape_node(node: om2.MObject) -> bool:
    """Whether the node is a Shape node."""
    return node.hasFn(om2.MFn.kShape)


def is_transform_node(node: om2.MObject) -> bool:
    """Whether the node is a Transform node."""
    return node.hasFn(om2.MFn.kTransform)


def dag_path_for(node: om2.MObject) -> Optional[om2.MDagPath]:
    """Get the node's first DAG path; return None for non-DAG nodes."""
    if not is_dag_node(node):
        return None
    try:
        return om2.MFnDagNode(node).getPath()
    except RuntimeError:
        return None


def qualified_node_name(node: om2.MObject) -> str:
    """The node's unique qualified name: full path for DAG nodes, unique name for DG nodes.

    The full path avoids writing to the wrong target when node names collide
    (``CubeA`` and ``|GRP|CubeA``); this is a correctness prerequisite for batch
    writes.
    """
    path = dag_path_for(node)
    if path is not None:
        try:
            return path.fullPathName()
        except RuntimeError:
            pass
    return node_display_name(node)


def plug_attribute_path(plug: om2.MPlug) -> str:
    """The plug's attribute path (long name, necessary indices, no node name).

    For example ``translateX``, ``warr[3]``.
    """
    try:
        return plug.partialName(*_PARTIAL_LONG)
    except (RuntimeError, TypeError):
        # Fallback: cut the attribute part out of plug.name() (Maya attribute
        # names themselves contain no ".")
        name = plug.name()
        _, _, attribute = name.partition(".")
        return attribute


def qualified_plug_name(node: om2.MObject, plug: om2.MPlug) -> str:
    """The full target name used for batch writes, e.g. ``|GRP|CubeA.translateX``."""
    return f"{qualified_node_name(node)}.{plug_attribute_path(plug)}"


def iter_attributes(dep: om2.MFnDependencyNode) -> Iterator[om2.MObject]:
    """Iterate over all attribute MObjects on a node.

    Note: this is the **only** safe way to enumerate attributes.
    ``findPlug("nonexistent", False)`` raises
    ``RuntimeError: (kInvalidParameter)``, so findPlug cannot be used to probe
    for existence.
    """
    for index in range(dep.attributeCount()):
        yield dep.attribute(index)


def find_attribute(dep: om2.MFnDependencyNode, name: str) -> Optional[om2.MObject]:
    """Get an attribute MObject by name; return None when it does not exist.

    ``MFnDependencyNode.attribute()`` does not raise for a nonexistent attribute;
    instead it returns an MObject with ``isNull() == True``, which is exactly the
    safe way to probe for existence.
    """
    try:
        attribute = dep.attribute(name)
    except RuntimeError:
        return None
    if attribute is None or attribute.isNull():
        return None
    return attribute


def find_plug(dep: om2.MFnDependencyNode, attribute: om2.MObject,
              networked: bool = False) -> Optional[om2.MPlug]:
    """Get the MPlug from an attribute MObject known to exist; return None on failure."""
    try:
        return dep.findPlug(attribute, networked)
    except RuntimeError:
        return None


def child_plugs(plug: om2.MPlug) -> List[om2.MPlug]:
    """Child plug list of a compound plug (access by index, never guess names).

    Measured: for the same color attribute, the child attribute names vary with
    the attribute (``colorR`` / ``overrideColorR`` / ``objectColorR``); only the
    index is a stable structure.
    """
    if not plug.isCompound:
        return []
    try:
        return [plug.child(index) for index in range(plug.numChildren())]
    except (RuntimeError, TypeError):
        return []


def existing_element_indices(plug: om2.MPlug) -> List[int]:
    """Existing logical indices on an array plug (ascending)."""
    if not plug.isArray:
        return []
    try:
        return sorted(plug.getExistingArrayAttributeIndices())
    except (RuntimeError, TypeError):
        return []


def plug_is_null(plug: Optional[om2.MPlug]) -> bool:
    """Safely determine whether a plug is null."""
    if plug is None:
        return True
    try:
        return bool(plug.isNull)
    except RuntimeError:
        return True


def maya_version() -> str:
    """Maya version string."""
    from maya import cmds

    return cmds.about(version=True)


def scene_node_count() -> int:
    """Scene node count (a cheap check used for cache invalidation)."""
    from maya import cmds

    try:
        return len(cmds.ls(long=True) or [])
    except RuntimeError:
        return -1
