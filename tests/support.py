"""Test support: scene fixtures and assertion helpers for mayapy.

Design notes (all measured, see section 9 of docs/ARCHITECTURE.md):

* Colour management fails to initialize on this machine, so
  ``cmds.addAttr(attributeType="float3")`` **fails silently**; the Color3 test
  data therefore uses a colour attribute that **really exists**
  (``overrideColorRGB`` on a transform) instead of creating one dynamically.
* ``double3`` dynamic attributes fail to create as well, so the "custom
  three-component vector" is simulated with a compound + 3 children; the real
  VECTOR3 case is tested with the built-in ``translate``.
"""

from __future__ import annotations

from typing import Dict, List, Optional

_INITIALIZED = False

#: Custom attributes added to every test node
CUSTOM_ATTRIBUTES = (
    ("customFloat", {"attributeType": "float", "keyable": True}),
    ("customInt", {"attributeType": "long", "keyable": True}),
    ("customBool", {"attributeType": "bool", "keyable": True}),
    ("customString", {"dataType": "string"}),
    ("customEnum", {"attributeType": "enum", "enumName": "Off:Low:Medium:High"}),
    ("customAngle", {"attributeType": "doubleAngle", "keyable": True}),
    ("customDistance", {"attributeType": "doubleLinear", "keyable": True}),
)


def ensure_maya():
    """Initialize ``maya.standalone`` (idempotent).

    **Critical**: calling ``maya.standalone.initialize()`` twice breaks the
    current scene, so first probe whether Maya is already available; the run
    entry point (``run_tests.py``) goes through here too, so the whole process
    initializes exactly once.
    """
    global _INITIALIZED
    if not _INITIALIZED:
        if not _maya_ready():
            import maya.standalone

            maya.standalone.initialize(name="python")
        _INITIALIZED = True

    from maya import cmds

    cmds.undoInfo(state=True, infinity=True)
    return cmds


def _maya_ready() -> bool:
    """Probe whether the Maya kernel is already initialized and usable."""
    try:
        from maya import cmds

        cmds.about(version=True)
        return True
    except Exception:  # noqa: BLE001 - several exception types are possible before initialization
        return False


def new_scene():
    """Create an empty scene and clear the Undo queue."""
    cmds = ensure_maya()
    cmds.file(new=True, force=True)
    cmds.flushUndo()
    return cmds


def add_custom_attributes(node: str, include_label: bool = True) -> None:
    """Add a set of custom attributes to a node (covering every scalar type)."""
    cmds = ensure_maya()
    for name, kwargs in CUSTOM_ATTRIBUTES:
        _safe_add_attribute(cmds, node, name, **kwargs)
    if include_label:
        _safe_add_attribute(cmds, node, "customLabel", dataType="string")
    # compound: simulates a custom vector (dynamic double3 creation fails in this environment)
    _safe_add_attribute(cmds, node, "customVector", attributeType="compound", numberOfChildren=3)
    for suffix in ("X", "Y", "Z"):
        _safe_add_attribute(cmds, node, "customVector" + suffix, attributeType="double",
                            parent="customVector")
    # multi: already existing array elements
    _safe_add_attribute(cmds, node, "customMulti", attributeType="float", multi=True)
    cmds.setAttr(f"{node}.customMulti[0]", 1.0)
    cmds.setAttr(f"{node}.customMulti[1]", 2.0)


def _safe_add_attribute(cmds, node: str, name: str, **kwargs) -> bool:
    """Add an attribute; returns False if it already exists or the environment rejects it (never raises)."""
    try:
        if cmds.attributeQuery(name, node=node, exists=True):
            return False
        cmds.addAttr(node, longName=name, **kwargs)
    except RuntimeError:
        return False
    return bool(cmds.attributeQuery(name, node=node, exists=True))


def build_scene() -> Dict[str, object]:
    """Build the layered scene that covers every test requirement.

    Structure::

        BatchTest_GRP
        ├── GroupA_GRP
        │   ├── CubeA (mesh + shape)
        │   │   └── LocA (locator + shape)
        │   └── CubeB (mesh + shape + intermediate shape)
        ├── GroupB_GRP
        │   └── CubeC (mesh + shape)
        └── Deep_GRP / L1_GRP / L2_GRP / CubeD (deep hierarchy)

    ``customLabel`` is added to only some of the nodes, so it can be used to
    test "missing attribute".
    """
    cmds = new_scene()

    root = cmds.group(em=True, name="BatchTest_GRP")
    group_a = cmds.group(em=True, name="GroupA_GRP", parent=root)
    group_b = cmds.group(em=True, name="GroupB_GRP", parent=root)

    cube_a = cmds.polyCube(name="CubeA")[0]
    cmds.parent(cube_a, group_a)
    cube_b = cmds.polyCube(name="CubeB")[0]
    cmds.parent(cube_b, group_a)
    cube_c = cmds.polyCube(name="CubeC")[0]
    cmds.parent(cube_c, group_b)

    loc_a = cmds.spaceLocator(name="LocA")[0]
    cmds.parent(loc_a, cube_a)

    # deep hierarchy
    deep = cmds.group(em=True, name="Deep_GRP", parent=root)
    level1 = cmds.group(em=True, name="L1_GRP", parent=deep)
    level2 = cmds.group(em=True, name="L2_GRP", parent=level1)
    cube_d = cmds.polyCube(name="CubeD")[0]
    cmds.parent(cube_d, level2)

    # intermediate shape: parented under CubeB only
    intermediate = cmds.createNode("mesh", name="CubeBIntermediateshape", parent=cube_b)
    cmds.setAttr(f"{intermediate}.intermediateObject", True)

    transforms = [root, group_a, group_b, cube_a, cube_b, cube_c, loc_a,
                  deep, level1, level2, cube_d]
    for node in transforms:
        add_custom_attributes(node, include_label=(node != cube_c))

    # attributes used for the lock and connection cases
    for node in transforms:
        _safe_add_attribute(cmds, node, "lockedFloat", attributeType="float", keyable=True)
        _safe_add_attribute(cmds, node, "drivenFloat", attributeType="float", keyable=True)
    cmds.setAttr(f"{cube_a}.lockedFloat", lock=True)
    cmds.connectAttr(f"{cube_b}.customFloat", f"{cube_a}.drivenFloat")

    shapes = {}
    for node in (cube_a, cube_b, cube_c, cube_d, loc_a):
        found = cmds.listRelatives(node, shapes=True) or []
        if found:
            shapes[node] = found[0]

    cmds.flushUndo()
    return {
        "root": root,
        "group_a": group_a,
        "group_b": group_b,
        "cube_a": cube_a,
        "cube_b": cube_b,
        "cube_c": cube_c,
        "cube_d": cube_d,
        "loc_a": loc_a,
        "deep": deep,
        "level1": level1,
        "level2": level2,
        "intermediate": intermediate,
        "transforms": transforms,
        "shapes": shapes,
    }


def make_shader() -> str:
    """Create a lambert (a non-DAG node) for the DG node and real Color3 tests."""
    cmds = ensure_maya()
    return cmds.shadingNode("lambert", asShader=True, name="BatchTestLambert")


def node_names(records) -> List[str]:
    """NodeRecord list -> list of short names."""
    return [record.display_name for record in records]


def has_attribute(node: str, attribute: str) -> bool:
    """Whether the attribute exists."""
    cmds = ensure_maya()
    try:
        return bool(cmds.attributeQuery(attribute, node=node, exists=True))
    except RuntimeError:
        return False


def full_path(name: str) -> str:
    """Full DAG path of the node."""
    cmds = ensure_maya()
    found = cmds.ls(name, long=True) or []
    return found[0] if found else name


def get_value(node: str, attribute: str) -> Optional[object]:
    """Read an attribute value (returns None on failure)."""
    cmds = ensure_maya()
    try:
        return cmds.getAttr(f"{node}.{attribute}")
    except (RuntimeError, ValueError):
        return None
