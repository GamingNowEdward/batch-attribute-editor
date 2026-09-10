"""Compatibility validation tests (requirement sections 16-20).

Covers: Missing / Locked / Connected / type mismatch, plus the trap where a
compound parent plug looks writable while only one of its child plugs is
connected.
"""

from __future__ import annotations

import unittest

from core.compatibility import (
    CompatibilityValidator,
    ValidationStatus,
)
from core.traversal import DagTraversal
from core.type_resolver import build_channels
from core.types import AttributeKind
from tests import support
from utils import maya_utils


def make_record(node_name: str):
    """Build a NodeRecord from a node name."""
    mobject = maya_utils.find_node(node_name)
    assert mobject is not None, node_name
    return DagTraversal.make_record(mobject)


def validate(node_name: str, attribute: str, with_channels: bool = True):
    """Convenience wrapper: validate one attribute on one node."""
    record = make_record(node_name)
    dep = maya_utils.dependency_node(record.node)
    attribute_object = maya_utils.find_attribute(dep, attribute)
    channels = ()
    if with_channels and attribute_object is not None:
        plug = maya_utils.find_plug(dep, attribute_object)
        from core.type_resolver import TypeResolver

        definition = TypeResolver.describe_attribute(attribute_object, plug)
        channels = build_channels(plug, definition)
    return CompatibilityValidator.validate(record, attribute, None, channels)


class CompatibilityTest(unittest.TestCase):
    """Writability decisions."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = support.build_scene()
        cls.cmds = support.ensure_maya()

    def test_writable_attribute_is_ok(self) -> None:
        """An ordinary attribute must be judged writable."""
        result = validate(self.scene["cube_b"], "customFloat")
        self.assertTrue(result.is_ok)
        self.assertTrue(result.has_writable_channel)

    def test_missing_attribute_is_detected(self) -> None:
        """19. A missing attribute must be reported as Missing instead of raising."""
        result = validate(self.scene["cube_a"], "noSuchAttributeHere")
        self.assertIn(ValidationStatus.MISSING, result.statuses)
        self.assertFalse(result.has_writable_channel)
        self.assertIn("Attribute missing", result.skip_reason())

    def test_locked_attribute_is_skipped(self) -> None:
        """18. Locked attributes are not modified by default and come with a reason (no automatic unlock)."""
        cube_a = self.scene["cube_a"]
        self.cmds.setAttr(f"{cube_a}.lockedFloat", lock=True)
        result = validate(cube_a, "lockedFloat")
        self.assertFalse(result.has_writable_channel)
        statuses = [state.status for state in result.blocked_channels]
        self.assertIn(ValidationStatus.LOCKED, statuses)
        self.assertIn("Locked", result.skip_reason())
        # validation must never change the locked state
        self.assertTrue(self.cmds.getAttr(f"{cube_a}.lockedFloat", lock=True))
        self.cmds.setAttr(f"{cube_a}.lockedFloat", lock=False)

    def test_unlocked_attribute_passes_again(self) -> None:
        """Writability returns after unlocking (validation leaves no side effects)."""
        cube_b = self.scene["cube_b"]
        self.cmds.setAttr(f"{cube_b}.lockedFloat", lock=True)
        self.assertFalse(validate(cube_b, "lockedFloat").has_writable_channel)
        self.cmds.setAttr(f"{cube_b}.lockedFloat", lock=False)
        self.assertTrue(validate(cube_b, "lockedFloat").has_writable_channel)

    def test_connected_attribute_is_skipped(self) -> None:
        """17. Connected attributes are not modified by default and the connection is **not** broken automatically."""
        cube_a = self.scene["cube_a"]
        cube_b = self.scene["cube_b"]
        if not self.cmds.isConnected(f"{cube_b}.customFloat", f"{cube_a}.drivenFloat"):
            self.cmds.connectAttr(f"{cube_b}.customFloat", f"{cube_a}.drivenFloat")
        result = validate(cube_a, "drivenFloat")
        self.assertFalse(result.has_writable_channel)
        statuses = [state.status for state in result.blocked_channels]
        self.assertIn(ValidationStatus.CONNECTED, statuses)
        # the connection must stay exactly as it was
        self.assertTrue(self.cmds.isConnected(f"{cube_b}.customFloat", f"{cube_a}.drivenFloat"))
        self.cmds.disconnectAttr(f"{cube_b}.customFloat", f"{cube_a}.drivenFloat")

    def test_source_attribute_is_writable(self) -> None:
        """An attribute used as the connection **source** is still writable.

        Measured: ``plug.isConnected`` is True for both the source and the
        destination, so it cannot be used as a "not writable" test - only
        ``isDestination`` means the write has no effect. This test uses its own
        scene and does not depend on whether other tests disconnected anything.
        """
        cmds = self.cmds
        node_a = cmds.group(em=True, name="SourceNodeA")
        node_b = cmds.group(em=True, name="SourceNodeB")
        for node in (node_a, node_b):
            cmds.addAttr(node, longName="srcFloat", attributeType="float", keyable=True)
        cmds.connectAttr(f"{node_a}.srcFloat", f"{node_b}.srcFloat")

        source = validate(node_a, "srcFloat")
        self.assertTrue(source.has_writable_channel, "A connection source should be writable")

        destination = validate(node_b, "srcFloat")
        self.assertFalse(destination.has_writable_channel, "A connection destination is not writable")

        cmds.disconnectAttr(f"{node_a}.srcFloat", f"{node_b}.srcFloat")

    def test_compound_parent_with_connected_child_is_detected(self) -> None:
        """A compound parent plug reports isConnected False, but a connected child plug must be detected.

        Measured: ``plug.isConnected`` is False while ``isFreeToChange()``
        returns ``kChildrenNotFreeToChange(2)``; looking at the parent plug alone
        misses this and the write then fails.
        """
        cmds = self.cmds
        node = cmds.group(em=True, name="CompoundConnectNode")
        source = cmds.group(em=True, name="CompoundConnectSource")
        cmds.addAttr(node, longName="comp", attributeType="compound", numberOfChildren=2)
        cmds.addAttr(node, longName="compA", attributeType="float", parent="comp", keyable=True)
        cmds.addAttr(node, longName="compB", attributeType="float", parent="comp", keyable=True)
        cmds.addAttr(source, longName="out", attributeType="float", keyable=True)
        cmds.connectAttr(f"{source}.out", f"{node}.compA")

        result = validate(node, "comp")
        blocked = {state.channel.display_label: state.status for state in result.blocked_channels}
        self.assertIn(ValidationStatus.CONNECTED, blocked.values(),
                      "A connected child plug must be recognised as not writable")
        # compB is not connected and must stay writable (compound channel labels drop the parent attribute name prefix)
        writable = {state.channel.display_label for state in result.writable_channels}
        self.assertIn("B", writable)

    def test_type_mismatch_is_detected(self) -> None:
        """20. Nodes with the same name but a different type must be judged a type mismatch."""
        cmds = self.cmds
        node = cmds.group(em=True, name="MismatchNode")
        cmds.addAttr(node, longName="mixed", attributeType="long", keyable=True)

        # the expected type is float, the actual type is int
        from core.types import AttributeDefinition

        expected = AttributeDefinition(
            name="mixed", short_name="mixed", kind=AttributeKind.FLOAT,
            api_type="kNumericAttribute", numeric_type=11,
        )
        result = CompatibilityValidator.validate(make_record(node), "mixed", expected, ())
        self.assertIn(ValidationStatus.TYPE_MISMATCH, result.statuses)

    def test_deleted_node_is_reported_as_missing(self) -> None:
        """A deleted node must be judged not writable (a stale MObject returns outdated data and cannot be trusted)."""
        cmds = self.cmds
        node = cmds.group(em=True, name="DeleteMeNode")
        cmds.addAttr(node, longName="tempFloat", attributeType="float", keyable=True)
        record = make_record(node)
        self.assertTrue(record.is_alive())

        cmds.delete(node)
        self.assertFalse(record.is_alive())
        result = CompatibilityValidator.validate(record, "tempFloat", None, ())
        self.assertIn(ValidationStatus.NODE_MISSING, result.statuses)

    def test_renamed_node_is_still_writable(self) -> None:
        """A renamed node must still be re-checked and written correctly (the point of the UUID re-check)."""
        cmds = self.cmds
        node = cmds.group(em=True, name="WillBeRenamed")
        cmds.addAttr(node, longName="renameFloat", attributeType="float", keyable=True)
        record = make_record(node)

        renamed = cmds.rename(node, "RenamedTarget")
        self.assertTrue(record.is_alive())
        result = CompatibilityValidator.validate(record, "renameFloat", None, ())
        self.assertTrue(result.has_writable_channel)
        self.assertEqual(result.target_base, f"|{renamed}", "The write target must use the current name from the re-check")

    def test_shape_attribute_is_validated(self) -> None:
        """Attributes on Shape nodes can be validated too (Shape support is a key requirement)."""
        shape = self.scene["shapes"][self.scene["cube_a"]]
        result = validate(shape, "visibility")
        self.assertTrue(result.has_writable_channel)


if __name__ == "__main__":
    unittest.main()
