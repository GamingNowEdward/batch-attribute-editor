"""Traversal and selection resolution tests (requirement section 35 items 1-6, 21-22)."""

from __future__ import annotations

import unittest

from core.selection import SelectionManager
from core.traversal import DagTraversal, TraversalScope
from tests import support


class TraversalTest(unittest.TestCase):
    """Node traversal: Shape, Intermediate, deep hierarchy, deduplication."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = support.build_scene()

    def _collect(self, node_names, scope=TraversalScope.SELECTION_AND_DESCENDANTS):
        result = SelectionManager.resolve(node_names)
        records = DagTraversal.collect([record.node for record in result.roots], scope)
        return result, records

    def test_single_transform_includes_its_shape(self) -> None:
        """1/2. A single Transform must bring its own Shape along."""
        _, records = self._collect([self.scene["cube_a"]])
        names = support.node_names(records)
        self.assertIn("CubeA", names)
        self.assertIn("CubeAShape", names)

    def test_descendants_include_nested_locator_and_shape(self) -> None:
        """A Locator nested in the hierarchy and its Shape must be found too."""
        _, records = self._collect([self.scene["cube_a"]])
        names = support.node_names(records)
        self.assertIn("LocA", names)
        self.assertIn("LocAShape", names)

    def test_intermediate_shape_is_included(self) -> None:
        """21. Intermediate Shapes must be in the result and correctly flagged."""
        _, records = self._collect([self.scene["group_a"]])
        intermediates = [record for record in records if record.is_intermediate]
        self.assertEqual(len(intermediates), 1)
        self.assertEqual(intermediates[0].display_name, "CubeBIntermediateshape")
        self.assertTrue(intermediates[0].is_shape)

    def test_selection_only_scope(self) -> None:
        """Current selection only: descendants are not expanded, but the root itself is still returned."""
        _, records = self._collect([self.scene["group_a"]], TraversalScope.SELECTION_ONLY)
        names = support.node_names(records)
        self.assertEqual(names, ["GroupA_GRP"])

    def test_deep_hierarchy(self) -> None:
        """4. The deep hierarchy (5 levels) must be traversed in full."""
        _, records = self._collect([self.scene["root"]])
        names = support.node_names(records)
        for expected in ("Deep_GRP", "L1_GRP", "L2_GRP", "CubeD", "CubeDShape"):
            self.assertIn(expected, names)

        cube_d = [record for record in records if record.display_name == "CubeD"][0]
        root = [record for record in records if record.display_name == "BatchTest_GRP"][0]
        self.assertGreater(cube_d.depth, root.depth + 3)

    def test_multiple_roots_all_collected(self) -> None:
        """3. Every selected root node must be processed."""
        _, records = self._collect([self.scene["group_a"], self.scene["group_b"]])
        names = support.node_names(records)
        self.assertIn("CubeA", names)
        self.assertIn("CubeC", names)

    def test_duplicate_selection_is_deduplicated(self) -> None:
        """5. When a parent and its descendant are both selected, the descendant must not be processed twice."""
        result, records = self._collect([self.scene["root"], self.scene["cube_a"]])
        self.assertEqual(len(result.roots), 1, "Duplicate roots must be deduplicated")
        self.assertEqual(result.covered, [support.full_path(self.scene["cube_a"])])

        names = support.node_names(records)
        self.assertEqual(len(names), len(set(names)), "Traversal results must not contain duplicate nodes")
        self.assertEqual(names.count("CubeA"), 1)

    def test_same_node_selected_twice(self) -> None:
        """The same node selected twice is still processed only once."""
        _, records = self._collect([self.scene["cube_a"], self.scene["cube_a"]])
        names = support.node_names(records)
        self.assertEqual(names.count("CubeA"), 1)

    def test_non_dag_node_without_descendants(self) -> None:
        """A non-DAG node (shader) has no descendants, but that must not make traversal fail."""
        shader = support.make_shader()
        _, records = self._collect([shader])
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0].node_type, "lambert")
        self.assertFalse(records[0].is_dag)

    def test_shape_nodes_are_present_for_every_mesh(self) -> None:
        """The shape of every mesh must appear in the result."""
        _, records = self._collect([self.scene["root"]])
        names = set(support.node_names(records))
        for expected in ("CubeAShape", "CubeBShape", "CubeCShape", "CubeDShape"):
            self.assertIn(expected, names)

    def test_missing_node_is_reported_not_crashed(self) -> None:
        """A non-existent node name must be ignored with a reason instead of raising."""
        result = SelectionManager.resolve(["NoSuchNode_XYZ"])
        self.assertTrue(result.is_empty)
        self.assertEqual(len(result.ignored), 1)

    def test_record_stays_alive_flag(self) -> None:
        """is_alive must become False after the node is deleted (the pre-Apply existence re-check relies on it)."""
        cmds = support.ensure_maya()
        temp = cmds.group(em=True, name="TempDeleteMe")
        _, records = self._collect([temp])
        record = records[0]
        self.assertTrue(record.is_alive())
        cmds.delete(temp)
        self.assertFalse(record.is_alive())


if __name__ == "__main__":
    unittest.main()
