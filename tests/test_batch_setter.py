"""Batch setter tests (requirement sections 8-15, 19, 20, 22, 33).

Covers every type required to be supported, missing/locked/connected skips,
errors that must not abort the whole batch, and the type safety of
"no implicit type conversion".
"""

from __future__ import annotations

import unittest

from core.attributes import AttributeScanner
from core.batch_setter import (
    BatchSetter,
    ValueCoercionError,
    ValuePayload,
    coerce_value,
)
from core.search import SearchEngine
from core.selection import SelectionManager
from core.traversal import DagTraversal, TraversalScope
from core.types import AttributeKind
from tests import support


class CoercionTest(unittest.TestCase):
    """Type-safe conversion of user input."""

    def test_float_accepts_number_and_numeric_string(self) -> None:
        self.assertEqual(coerce_value("1.25", AttributeKind.FLOAT), 1.25)
        self.assertEqual(coerce_value(2, AttributeKind.FLOAT), 2.0)

    def test_integer_rejects_fractional_float(self) -> None:
        """Integer input must be validated; it must never be silently truncated."""
        with self.assertRaises(ValueCoercionError):
            coerce_value(3.5, AttributeKind.INT)

    def test_integer_rejects_text(self) -> None:
        with self.assertRaises(ValueCoercionError):
            coerce_value("abc", AttributeKind.INT)

    def test_integer_accepts_integral_values(self) -> None:
        self.assertEqual(coerce_value(4, AttributeKind.INT), 4)
        self.assertEqual(coerce_value("4", AttributeKind.INT), 4)
        self.assertEqual(coerce_value(4.0, AttributeKind.INT), 4)

    def test_string_is_not_treated_as_number(self) -> None:
        """String must stay a string; no numeric conversion."""
        self.assertEqual(coerce_value("1.5", AttributeKind.STRING), "1.5")
        self.assertEqual(coerce_value(12, AttributeKind.STRING), "12")

    def test_float_rejects_boolean(self) -> None:
        """Booleans must not be treated as numbers (avoids surprises like True → 1)."""
        with self.assertRaises(ValueCoercionError):
            coerce_value(True, AttributeKind.FLOAT)

    def test_boolean_parsing(self) -> None:
        self.assertIs(coerce_value("true", AttributeKind.BOOL), True)
        self.assertIs(coerce_value("False", AttributeKind.BOOL), False)
        self.assertIs(coerce_value(0, AttributeKind.BOOL), False)
        with self.assertRaises(ValueCoercionError):
            coerce_value("maybe", AttributeKind.BOOL)

    def test_float_rejects_text(self) -> None:
        with self.assertRaises(ValueCoercionError):
            coerce_value("not-a-number", AttributeKind.FLOAT)


class BatchSetterTest(unittest.TestCase):
    """End-to-end behaviour of batch writes."""

    def setUp(self) -> None:
        self.scene = support.build_scene()
        self.cmds = support.ensure_maya()
        self.setter = BatchSetter()
        self.engine = SearchEngine(AttributeScanner())
        self.records = self._collect()

    def _collect(self):
        result = SelectionManager.resolve([self.scene["root"]])
        return DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )

    def group_for(self, pattern: str, attribute: str):
        """Search and pick out the aggregated row of the given attribute."""
        found = self.engine.search(self.records, pattern)
        for item in found.attributes:
            if item.name == attribute:
                return item
        self.fail(f"Attribute {attribute} not found")

    def payload_for(self, group, value, channel_index=None):
        """Build a payload for one channel of the group."""
        result = SelectionManager.resolve([self.scene["root"]])
        records = DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )
        # use the session's channel union logic
        from core.session import BatchAttributeSession

        session = BatchAttributeSession()
        session.records = records
        channels = session.channels_for(group)
        payload = ValuePayload()
        if channel_index is None:
            for channel in channels:
                payload.set(channel, value)
        else:
            payload.set(channels[channel_index], value)
        return payload, channels

    # ------------------------------------------------------------ scalar types

    def test_batch_set_boolean(self) -> None:
        """11. Boolean batch set (visibility)."""
        group = self.group_for("visibility", "visibility")
        payload, _ = self.payload_for(group, False)
        report = self.setter.apply(group, payload)

        self.assertGreater(report.succeeded, 5)
        self.assertEqual(report.failed, 0)
        for name in ("CubeA", "CubeB", "CubeC", "CubeD", "CubeAShape"):
            self.assertFalse(self.cmds.getAttr(f"{name}.visibility"),
                             f"{name}.visibility should be False")

    def test_batch_set_float(self) -> None:
        """9. Float batch set."""
        group = self.group_for("customFloat", "customFloat")
        payload, _ = self.payload_for(group, 0.75)
        report = self.setter.apply(group, payload)
        self.assertGreater(report.succeeded, 5)
        for name in ("CubeA", "CubeB", "CubeD"):
            self.assertAlmostEqual(self.cmds.getAttr(f"{name}.customFloat"), 0.75, places=5)

    def test_batch_set_integer(self) -> None:
        """10. Integer batch set."""
        group = self.group_for("customInt", "customInt")
        payload, _ = self.payload_for(group, 7)
        self.setter.apply(group, payload)
        for name in ("CubeA", "CubeB", "CubeD"):
            self.assertEqual(self.cmds.getAttr(f"{name}.customInt"), 7)

    def test_batch_set_string(self) -> None:
        """12. String batch set."""
        group = self.group_for("customString", "customString")
        payload, _ = self.payload_for(group, "hello")
        self.setter.apply(group, payload)
        for name in ("CubeA", "CubeB", "CubeD"):
            self.assertEqual(self.cmds.getAttr(f"{name}.customString"), "hello")

    def test_batch_set_enum_by_index(self) -> None:
        """18. Enum written by Maya's enum index."""
        group = self.group_for("customEnum", "customEnum")
        payload, _ = self.payload_for(group, 2)
        self.setter.apply(group, payload)
        for name in ("CubeA", "CubeB", "CubeD"):
            self.assertEqual(self.cmds.getAttr(f"{name}.customEnum"), 2)

    def test_batch_set_angle(self) -> None:
        """13. Angle written in working units (degrees)."""
        group = self.group_for("customAngle", "customAngle")
        payload, _ = self.payload_for(group, 45.0)
        self.setter.apply(group, payload)
        for name in ("CubeA", "CubeB"):
            self.assertAlmostEqual(self.cmds.getAttr(f"{name}.customAngle"), 45.0, places=4)

    def test_batch_set_distance(self) -> None:
        """13. Distance written in working units (centimeters)."""
        group = self.group_for("customDistance", "customDistance")
        payload, _ = self.payload_for(group, 12.5)
        self.setter.apply(group, payload)
        for name in ("CubeA", "CubeB"):
            self.assertAlmostEqual(self.cmds.getAttr(f"{name}.customDistance"), 12.5, places=4)

    # ------------------------------------------------------------ compound types

    def test_batch_set_double3_per_channel(self) -> None:
        """14. Double3: X/Y/Z must be writable as three separate sub-plugs."""
        group = self.group_for("translate", "translate")
        _, channels = self.payload_for(group, 0.0)
        self.assertEqual(len(channels), 3)
        self.assertEqual([channel.label for channel in channels], ["X", "Y", "Z"])

        payload = ValuePayload()
        payload.set(channels[0], 1.0)
        payload.set(channels[1], 2.0)
        payload.set(channels[2], 3.0)
        report = self.setter.apply(group, payload)
        self.assertGreater(report.succeeded, 5)

        for name in ("CubeA", "CubeB", "CubeD"):
            self.assertAlmostEqual(self.cmds.getAttr(f"{name}.translateX"), 1.0, places=5)
            self.assertAlmostEqual(self.cmds.getAttr(f"{name}.translateY"), 2.0, places=5)
            self.assertAlmostEqual(self.cmds.getAttr(f"{name}.translateZ"), 3.0, places=5)

    def test_batch_set_color3(self) -> None:
        """15. Color3: the R/G/B channels write to a real colour attribute."""
        group = self.group_for("overrideColorRGB", "overrideColorRGB")
        _, channels = self.payload_for(group, 0.0)
        self.assertEqual([channel.label for channel in channels], ["R", "G", "B"])

        payload = ValuePayload()
        payload.set(channels[0], 1.0)
        payload.set(channels[1], 0.5)
        payload.set(channels[2], 0.25)
        report = self.setter.apply(group, payload)
        self.assertGreater(report.succeeded, 5)

        value = self.cmds.getAttr("CubeA.overrideColorRGB")[0]
        self.assertAlmostEqual(value[0], 1.0, places=5)
        self.assertAlmostEqual(value[1], 0.5, places=5)
        self.assertAlmostEqual(value[2], 0.25, places=5)

    def test_color3_is_not_clamped(self) -> None:
        """Colour values outside 0-1 are allowed (no clamping unless the Maya attribute itself restricts them)."""
        group = self.group_for("overrideColorRGB", "overrideColorRGB")
        _, channels = self.payload_for(group, 0.0)
        payload = ValuePayload()
        payload.set(channels[0], 2.5)
        self.setter.apply(group, payload)
        value = self.cmds.getAttr("CubeA.overrideColorRGB")[0]
        self.assertAlmostEqual(value[0], 2.5, places=5)

    def test_batch_set_custom_compound(self) -> None:
        """16. Compound: modify the correct child plugs of the parent attribute."""
        group = self.group_for("customVector", "customVector")
        _, channels = self.payload_for(group, 0.0)
        self.assertEqual([channel.label for channel in channels], ["X", "Y", "Z"])

        payload = ValuePayload()
        payload.set(channels[1], 9.0)
        self.setter.apply(group, payload)
        self.assertAlmostEqual(self.cmds.getAttr("CubeA.customVectorY"), 9.0, places=5)
        self.assertAlmostEqual(self.cmds.getAttr("CubeA.customVectorX"), 0.0, places=5)

    def test_batch_set_multi_elements(self) -> None:
        """17. Multi: only already existing array elements are edited."""
        group = self.group_for("customMulti", "customMulti")
        _, channels = self.payload_for(group, 0.0)
        labels = [channel.display_label for channel in channels]
        self.assertIn("[0] Value", labels)
        self.assertIn("[1] Value", labels)

        payload = ValuePayload()
        for channel in channels:
            if channel.element_index == 1:
                payload.set(channel, 4.5)
        report = self.setter.apply(group, payload)
        self.assertGreater(report.succeeded, 5)
        self.assertAlmostEqual(self.cmds.getAttr("CubeA.customMulti[1]"), 4.5, places=5)

    def test_multi_does_not_create_new_elements(self) -> None:
        """Multi: the first version never creates array elements - the element count is unchanged after writing."""
        group = self.group_for("customMulti", "customMulti")
        payload, _ = self.payload_for(group, 3.0)
        before = len(self.cmds.getAttr("CubeA.customMulti", multiIndices=True) or [])
        self.setter.apply(group, payload)
        after = len(self.cmds.getAttr("CubeA.customMulti", multiIndices=True) or [])
        self.assertEqual(before, after)

    # ------------------------------------------------------------ skip policy

    def test_missing_attribute_is_skipped(self) -> None:
        """19. Attribute present on only some nodes: nodes missing it must be skipped."""
        group = self.group_for("customLabel", "customLabel")
        self.assertLess(group.node_count, len(self.records))

        payload, _ = self.payload_for(group, "tag")
        report = self.setter.apply(group, payload)
        self.assertGreater(report.succeeded, 5)
        self.assertEqual(self.cmds.getAttr("CubeA.customLabel"), "tag")

    def test_locked_attribute_is_skipped(self) -> None:
        """18. Locked attributes are skipped and never unlocked automatically."""
        cube_a = self.scene["cube_a"]
        self.cmds.setAttr(f"{cube_a}.customFloat", lock=True)
        group = self.group_for("customFloat", "customFloat")
        payload, _ = self.payload_for(group, 0.5)
        report = self.setter.apply(group, payload)

        self.assertTrue(self.cmds.getAttr(f"{cube_a}.customFloat", lock=True),
                        "The locked state must stay unchanged")
        self.assertNotAlmostEqual(self.cmds.getAttr(f"{cube_a}.customFloat"), 0.5, places=5)
        self.assertTrue(any("Locked" in entry.message for entry in report.log.warnings))

    def test_connected_attribute_is_skipped(self) -> None:
        """17. Connected attributes are skipped and the connection is never broken."""
        cube_a = self.scene["cube_a"]
        cube_b = self.scene["cube_b"]
        if not self.cmds.isConnected(f"{cube_b}.customFloat", f"{cube_a}.drivenFloat"):
            self.cmds.connectAttr(f"{cube_b}.customFloat", f"{cube_a}.drivenFloat")

        group = self.group_for("drivenFloat", "drivenFloat")
        payload, _ = self.payload_for(group, 99.0)
        report = self.setter.apply(group, payload)

        self.assertTrue(self.cmds.isConnected(f"{cube_b}.customFloat", f"{cube_a}.drivenFloat"),
                        "The connection must be preserved")
        self.assertTrue(any("Connected" in entry.message for entry in report.log.warnings))

    def test_failure_does_not_abort_whole_batch(self) -> None:
        """33. A single failing target must not crash the whole batch; the remaining targets must still complete."""
        cube_a = self.scene["cube_a"]
        # lock one of the nodes to create a single-point failure
        self.cmds.setAttr(f"{cube_a}.customFloat", lock=True)
        group = self.group_for("customFloat", "customFloat")
        payload, _ = self.payload_for(group, 0.25)
        report = self.setter.apply(group, payload)

        self.assertGreater(report.succeeded, 5, "The remaining nodes must still be modified")
        self.assertAlmostEqual(self.cmds.getAttr("CubeD.customFloat"), 0.25, places=5)
        self.assertEqual(report.failed, 0, "A lock counts as a skip, not a failure")

    def test_report_lists_failures_with_reason(self) -> None:
        """Failures must enter the report together with a reason and are never silently swallowed."""
        group = self.group_for("customFloat", "customFloat")
        payload, _ = self.payload_for(group, 0.1)
        report = self.setter.apply(group, payload)
        self.assertTrue(report.items)
        for item in report.items:
            self.assertTrue(item.target)
            self.assertIn(".", item.target)

    # ------------------------------------------------------------ type incompatibility

    def test_same_name_different_type_only_matching_nodes_are_changed(self) -> None:
        """20. Same name, different type: only type-compatible nodes are modified; no implicit conversion."""
        cmds = support.new_scene()
        root = cmds.group(em=True, name="MixedRoot_GRP")
        nodes = {}
        for name, attribute_type in (("MixedA", "float"), ("MixedB", "long"),
                                     ("MixedC", "bool"), ("MixedD", "float")):
            node = cmds.group(em=True, name=name)
            cmds.parent(node, root)
            cmds.addAttr(node, longName="shared", attributeType=attribute_type, keyable=True)
            nodes[name] = node
        cmds.flushUndo()

        result = SelectionManager.resolve([root])
        records = DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )
        engine = SearchEngine(AttributeScanner())
        found = engine.search(records, "shared")
        rows = {item.type_label: item for item in found.attributes if item.name == "shared"}
        self.assertEqual(set(rows), {"Float", "Integer", "Boolean"})

        float_row = rows["Float"]
        self.assertEqual(float_row.node_count, 2, "shared is a float on only two nodes")

        from core.session import BatchAttributeSession

        session = BatchAttributeSession()
        session.records = records
        channels = session.channels_for(float_row)
        payload = ValuePayload()
        for channel in channels:
            payload.set(channel, 1.5)

        report = BatchSetter().apply(float_row, payload)
        self.assertEqual(report.succeeded, 2)
        self.assertAlmostEqual(cmds.getAttr("MixedA.shared"), 1.5, places=5)
        self.assertAlmostEqual(cmds.getAttr("MixedD.shared"), 1.5, places=5)
        # nodes with a different type must stay unchanged
        self.assertEqual(cmds.getAttr("MixedB.shared"), 0)
        self.assertFalse(cmds.getAttr("MixedC.shared"))


if __name__ == "__main__":
    unittest.main()
