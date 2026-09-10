"""Type resolution tests (requirement section 35 items 9-21) - the most critical technical validation in this project.

What is asserted is the "real Maya type", not a type guessed from a value:
Float / Integer / Boolean / String / Enum / Angle / Distance /
Float3 / Double3 / Color3 / Compound / Multi / User Defined.
"""

from __future__ import annotations

import unittest

from core.attributes import AttributeScanner
from core.traversal import DagTraversal
from core.types import AttributeKind
from tests import support
from utils import maya_utils


class TypeResolutionTest(unittest.TestCase):
    """Attribute type resolution."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = support.build_scene()
        cls.cube = cls.scene["cube_a"]
        cls.shader = support.make_shader()
        cls.scanner = AttributeScanner()

    def describe(self, node: str, attribute: str):
        """Resolve the definition of an attribute on a node."""
        mobject = maya_utils.find_node(node)
        self.assertIsNotNone(mobject, f"Node {node} should exist")
        record = DagTraversal.make_record(mobject)
        return self.scanner.describe(record, attribute)

    # ------------------------------------------------------------ scalar types

    def test_boolean(self) -> None:
        """11. Boolean: visibility."""
        definition = self.describe(self.cube, "visibility")
        self.assertIsNotNone(definition)
        self.assertIs(definition.kind, AttributeKind.BOOL)
        self.assertEqual(definition.type_label, "Boolean")

    def test_float(self) -> None:
        """9. Float: a custom float attribute."""
        definition = self.describe(self.cube, "customFloat")
        self.assertIs(definition.kind, AttributeKind.FLOAT)
        self.assertEqual(definition.type_label, "Float")

    def test_integer(self) -> None:
        """10. Integer: a custom long attribute."""
        definition = self.describe(self.cube, "customInt")
        self.assertIs(definition.kind, AttributeKind.INT)
        self.assertEqual(definition.type_label, "Integer")

    def test_boolean_custom(self) -> None:
        """Boolean: a custom bool attribute."""
        definition = self.describe(self.cube, "customBool")
        self.assertIs(definition.kind, AttributeKind.BOOL)

    def test_string_is_not_float(self) -> None:
        """12. String must not be taken for Float."""
        definition = self.describe(self.cube, "customString")
        self.assertIs(definition.kind, AttributeKind.STRING)
        self.assertEqual(definition.type_label, "String")
        self.assertNotEqual(definition.kind, AttributeKind.FLOAT)

    def test_enum_with_fields(self) -> None:
        """18. Enum: the field names and their values must be read out in full."""
        definition = self.describe(self.cube, "customEnum")
        self.assertIs(definition.kind, AttributeKind.ENUM)
        self.assertEqual(definition.enum_labels(), ("Off", "Low", "Medium", "High"))
        self.assertEqual(dict(definition.enum_fields)["High"], 3)

    def test_angle_uses_unit_metadata(self) -> None:
        """13/14. Angle cannot simply be treated as an ordinary Float - the unit information is required."""
        definition = self.describe(self.cube, "customAngle")
        self.assertIs(definition.kind, AttributeKind.ANGLE)
        self.assertIsNotNone(definition.unit_type)
        self.assertEqual(definition.unit_type, 1)  # MFnUnitAttribute.kAngle

    def test_distance_uses_unit_metadata(self) -> None:
        """Distance carries unit information as well."""
        definition = self.describe(self.cube, "customDistance")
        self.assertIs(definition.kind, AttributeKind.DISTANCE)
        self.assertEqual(definition.unit_type, 2)  # MFnUnitAttribute.kDistance

    def test_time_unit(self) -> None:
        """Time unit attribute."""
        cmds = support.ensure_maya()
        node = self.scene["cube_d"]
        if not support.has_attribute(node, "customTime"):
            cmds.addAttr(node, longName="customTime", attributeType="time", keyable=True)
        definition = self.describe(node, "customTime")
        self.assertIs(definition.kind, AttributeKind.TIME)
        self.assertEqual(definition.unit_type, 3)  # MFnUnitAttribute.kTime

    # ------------------------------------------------------------ compound types

    def test_double3_vector(self) -> None:
        """14. Double3: translate must be VECTOR3, not Color3."""
        definition = self.describe(self.cube, "translate")
        self.assertIs(definition.kind, AttributeKind.VECTOR3)
        self.assertEqual(definition.type_label, "Double3")
        self.assertFalse(definition.is_color)
        self.assertEqual(len(definition.children), 3)
        self.assertEqual([child.name for child in definition.children],
                         ["translateX", "translateY", "translateZ"])

    def test_float3_vector_is_not_color(self) -> None:
        """Section 12: float3 must not be treated as a colour just because of its name - usedAsColor decides."""
        definition = self.describe(self.cube, "translate")
        self.assertFalse(definition.is_color, "translate is not a colour")

    def test_color3_on_transform(self) -> None:
        """15. Color3: overrideColorRGB on a transform."""
        definition = self.describe(self.cube, "overrideColorRGB")
        self.assertIs(definition.kind, AttributeKind.COLOR3)
        self.assertEqual(definition.type_label, "Color3")
        self.assertTrue(definition.is_color)
        self.assertEqual(len(definition.children), 3)

    def test_color3_on_shader(self) -> None:
        """15. Color3: lambert.color (a real shader colour attribute)."""
        definition = self.describe(self.shader, "color")
        self.assertIs(definition.kind, AttributeKind.COLOR3)
        self.assertTrue(definition.is_color)
        self.assertEqual([child.name for child in definition.children],
                         ["colorR", "colorG", "colorB"])

    def test_color_children_names_differ_but_indices_are_stable(self) -> None:
        """Colour child names vary (colorR / overrideColorR), so only the index can be used for access."""
        shader_color = self.describe(self.shader, "color")
        transform_color = self.describe(self.cube, "overrideColorRGB")
        self.assertNotEqual(shader_color.children[0].name, transform_color.children[0].name)

    def test_compound_attribute(self) -> None:
        """16. Compound: a custom compound + child attributes."""
        definition = self.describe(self.cube, "customVector")
        self.assertIs(definition.kind, AttributeKind.COMPOUND)
        self.assertTrue(definition.is_compound)
        self.assertEqual(len(definition.children), 3)
        self.assertEqual([child.name for child in definition.children],
                         ["customVectorX", "customVectorY", "customVectorZ"])
        for child in definition.children:
            self.assertIs(child.kind, AttributeKind.DOUBLE)

    def test_compound_child_flag(self) -> None:
        """Compound children are flagged so the "Hide compound children" filter can drop them."""
        parent = self.describe(self.cube, "translate")
        self.assertFalse(parent.is_compound_child)
        child = self.describe(self.cube, "translateX")
        self.assertTrue(child.is_compound_child)
        custom = self.describe(self.cube, "customVectorX")
        self.assertTrue(custom.is_compound_child)
        scalar = self.describe(self.cube, "visibility")
        self.assertFalse(scalar.is_compound_child)

    def test_multi_attribute(self) -> None:
        """17. Multi: a multi attribute must be flagged as an array, never treated as an ordinary scalar."""
        definition = self.describe(self.cube, "customMulti")
        self.assertTrue(definition.is_multi)
        self.assertIs(definition.kind, AttributeKind.FLOAT)

    def test_matrix_is_recognised_but_not_editable(self) -> None:
        """Matrix must be recognised but must not offer an editor (no pretending to support it)."""
        cmds = support.ensure_maya()
        node = self.scene["cube_c"]
        if not support.has_attribute(node, "customMatrix"):
            cmds.addAttr(node, longName="customMatrix", attributeType="matrix")
        definition = self.describe(node, "customMatrix")
        self.assertIs(definition.kind, AttributeKind.MATRIX)
        self.assertFalse(definition.supports_editing)

    # ------------------------------------------------------------ metadata

    def test_user_defined_flag(self) -> None:
        """20. User Defined Attributes must be recognised (via dynamic, not the non-existent userDefined)."""
        custom = self.describe(self.cube, "customFloat")
        builtin = self.describe(self.cube, "visibility")
        self.assertTrue(custom.is_dynamic)
        self.assertFalse(builtin.is_dynamic)

    def test_short_name_preserved(self) -> None:
        """The short name of visibility is v - short-name search depends on it."""
        definition = self.describe(self.cube, "visibility")
        self.assertEqual(definition.name, "visibility")
        self.assertEqual(definition.short_name, "v")

    def test_missing_attribute_returns_none(self) -> None:
        """19. A missing attribute must be reported as missing instead of raising."""
        definition = self.describe(self.cube, "definitelyNotAnAttribute")
        self.assertIsNone(definition)

    def test_hard_range_is_read(self) -> None:
        """The hard range Maya itself declares must be read (for hints, not for clamping)."""
        cmds = support.ensure_maya()
        node = self.scene["cube_d"]
        if not support.has_attribute(node, "boundedFloat"):
            cmds.addAttr(node, longName="boundedFloat", attributeType="float",
                         minValue=-2.0, maxValue=5.0, keyable=True)
        definition = self.describe(node, "boundedFloat")
        self.assertTrue(definition.has_min)
        self.assertTrue(definition.has_max)
        self.assertAlmostEqual(definition.min_value, -2.0, places=5)
        self.assertAlmostEqual(definition.max_value, 5.0, places=5)

    def test_unbounded_attribute_has_no_range(self) -> None:
        """A range must never be invented for an attribute without bounds."""
        cmds = support.ensure_maya()
        node = self.scene["cube_d"]
        if not support.has_attribute(node, "freeFloat"):
            cmds.addAttr(node, longName="freeFloat", attributeType="float", keyable=True)
        definition = self.describe(node, "freeFloat")
        self.assertFalse(definition.has_min)
        self.assertFalse(definition.has_max)

    def test_keyable_and_writable_flags(self) -> None:
        """keyable / writable flags."""
        keyable = self.describe(self.cube, "customFloat")
        self.assertTrue(keyable.is_keyable)
        self.assertTrue(keyable.is_writable)


if __name__ == "__main__":
    unittest.main()
