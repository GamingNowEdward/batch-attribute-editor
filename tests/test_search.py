"""Search and aggregation tests (requirement sections 5, 6, 20).

Covers: exact/partial/long-and-short-name/case-insensitive/fuzzy matching,
attribute-centric aggregation, and the rule that "same name, different type"
attributes must be split into separate result rows.
"""

from __future__ import annotations

import unittest

from core.attributes import AttributeScanner
from core.search import (
    MatchMode,
    NameMatcher,
    SearchEngine,
    SearchFilters,
)
from core.selection import SelectionManager
from core.traversal import DagTraversal, TraversalScope
from core.types import AttributeKind
from tests import support


class NameMatcherTest(unittest.TestCase):
    """Name matcher unit tests (no scene required)."""

    def test_contains_match(self) -> None:
        """Partial match: vis hits visibility."""
        self.assertTrue(NameMatcher("vis").matches("visibility", "v"))

    def test_case_insensitive(self) -> None:
        """Case insensitive."""
        self.assertTrue(NameMatcher("VISIBILITY").matches("visibility", "v"))
        self.assertTrue(NameMatcher("Visibility").matches("visibility", "v"))

    def test_short_name_match(self) -> None:
        """Short names match too."""
        self.assertTrue(NameMatcher("v", MatchMode.EXACT).matches("visibility", "v"))

    def test_exact_mode_rejects_partial(self) -> None:
        """Exact mode does not accept a partial hit."""
        self.assertFalse(NameMatcher("vis", MatchMode.EXACT).matches("visibility", "v"))
        self.assertTrue(NameMatcher("visibility", MatchMode.EXACT).matches("visibility", "v"))

    def test_prefix_mode(self) -> None:
        """Prefix match."""
        self.assertTrue(NameMatcher("vis", MatchMode.PREFIX).matches("visibility", "v"))
        self.assertFalse(NameMatcher("ility", MatchMode.PREFIX).matches("visibility", "v"))

    def test_fuzzy_mode(self) -> None:
        """Fuzzy match (subsequence)."""
        self.assertTrue(NameMatcher("vsblt", MatchMode.FUZZY).matches("visibility", "v"))
        self.assertFalse(NameMatcher("zzz", MatchMode.FUZZY).matches("visibility", "v"))

    def test_empty_pattern_matches_everything(self) -> None:
        """An empty pattern matches everything."""
        matcher = NameMatcher("")
        self.assertTrue(matcher.is_empty)
        self.assertTrue(matcher.matches("anything", "a"))


class SearchEngineTest(unittest.TestCase):
    """Search result aggregation."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = support.build_scene()

    def setUp(self) -> None:
        self.engine = SearchEngine(AttributeScanner())
        result = SelectionManager.resolve([self.scene["root"]])
        self.records = DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )
        self.assertGreater(len(self.records), 5)

    def find(self, result, name: str):
        for item in result.attributes:
            if item.name == name:
                return item
        return None

    def test_search_finds_visibility_across_hierarchy(self) -> None:
        """visibility should be found on many nodes in the hierarchy and aggregated into one row."""
        result = self.engine.search(self.records, "visibility")
        group = self.find(result, "visibility")
        self.assertIsNotNone(group, "visibility should be found")
        self.assertIs(group.definition.kind, AttributeKind.BOOL)
        self.assertGreaterEqual(group.node_count, 10, "most nodes in the hierarchy have visibility")

    def test_partial_search_finds_multiple_attributes(self) -> None:
        """A partial search for custom finds several custom attributes."""
        result = self.engine.search(self.records, "custom")
        names = {item.name for item in result.attributes}
        for expected in ("customFloat", "customInt", "customBool", "customString",
                         "customEnum", "customLabel", "customMulti"):
            self.assertIn(expected, names)

    def test_search_result_is_aggregated_not_per_node(self) -> None:
        """Results must be aggregated per attribute, not piled up as one row per node attribute."""
        result = self.engine.search(self.records, "customFloat")
        self.assertEqual(len(result.attributes), 1)
        group = result.attributes[0]
        self.assertGreater(group.node_count, 5)

    def test_type_is_reported_in_result(self) -> None:
        """Every row must carry the real type (the Type column in the UI)."""
        result = self.engine.search(self.records, "customFloat")
        self.assertEqual(result.attributes[0].type_label, "Float")
        boolean = self.find(self.engine.search(self.records, "visibility"), "visibility")
        self.assertEqual(boolean.type_label, "Boolean")

    def test_missing_attribute_on_some_nodes(self) -> None:
        """19. customLabel exists on only some nodes: node_count must be smaller than the total node count."""
        result = self.engine.search(self.records, "customLabel")
        group = self.find(result, "customLabel")
        self.assertIsNotNone(group)
        self.assertLess(group.node_count, len(self.records))

    def test_color_search_finds_color3(self) -> None:
        """Searching for color must find the real Color3 attribute and label its type correctly."""
        result = self.engine.search(self.records, "color")
        color = self.find(result, "overrideColorRGB")
        self.assertIsNotNone(color, "overrideColorRGB on a transform should be found")
        self.assertIs(color.definition.kind, AttributeKind.COLOR3)
        self.assertEqual(color.type_label, "Color3")

    def test_empty_pattern_lists_everything(self) -> None:
        """An empty pattern lists every attribute."""
        result = self.engine.search(self.records, "")
        self.assertGreater(len(result.attributes), 20)

    def test_filters_only_user_defined(self) -> None:
        """Filter: show only user-defined attributes."""
        filters = SearchFilters(only_user_defined=True)
        result = self.engine.search(self.records, "custom", filters)
        self.assertTrue(result.attributes)
        for item in result.attributes:
            self.assertTrue(item.definition.is_dynamic)

    def test_filters_hide_unsupported(self) -> None:
        """Filter: hide types that do not support editing."""
        filters = SearchFilters(hide_unsupported=True)
        result = self.engine.search(self.records, "", filters)
        for item in result.attributes:
            self.assertTrue(item.definition.supports_editing)

    def test_sorting_is_by_node_count_desc(self) -> None:
        """Results are sorted by node count descending so the user sees the widest-reaching attributes first."""
        result = self.engine.search(self.records, "")
        counts = [item.node_count for item in result.attributes]
        self.assertEqual(counts, sorted(counts, reverse=True))


class SameNameDifferentTypeTest(unittest.TestCase):
    """Section 20: same-name different-type attributes must be split into separate result rows."""

    @classmethod
    def setUpClass(cls) -> None:
        cmds = support.new_scene()
        cls.nodes = {}
        for name, attribute_type, value in (
            ("TypeNodeA", "float", 1.5),
            ("TypeNodeB", "long", 3),
            ("TypeNodeC", "bool", True),
        ):
            node = cmds.group(em=True, name=name)
            cmds.addAttr(node, longName="someAttr", attributeType=attribute_type, keyable=True)
            cmds.setAttr(f"{node}.someAttr", value)
            cls.nodes[name] = node
        cls.root = cmds.group(em=True, name="TypeRoot_GRP")
        for node in cls.nodes.values():
            cmds.parent(node, cls.root)
        cmds.flushUndo()

    def test_same_name_different_type_are_separate_rows(self) -> None:
        """someAttr must produce 3 rows (Float / Integer / Boolean), each holding only the matching nodes."""
        engine = SearchEngine(AttributeScanner())
        result = SelectionManager.resolve([self.root])
        records = DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )
        found = engine.search(records, "someAttr")
        rows = [item for item in found.attributes if item.name == "someAttr"]
        self.assertEqual(len(rows), 3, "Same name with different types must split into three rows")

        by_type = {row.type_label: row for row in rows}
        self.assertEqual(set(by_type), {"Float", "Integer", "Boolean"})
        for row in rows:
            self.assertEqual(row.node_count, 1, "Each row must contain only the node whose type matches")

    def test_other_type_count_is_reported(self) -> None:
        """Every row must be able to report "N more nodes have a different type"."""
        engine = SearchEngine(AttributeScanner())
        result = SelectionManager.resolve([self.root])
        records = DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )
        found = engine.search(records, "someAttr")
        for row in found.attributes:
            if row.name == "someAttr":
                self.assertEqual(row.other_type_total, 2)


class ChannelBoxKeyableFilterTest(unittest.TestCase):
    """The "Keyable only" filter must also keep channelBox attributes.

    Measured on Arnold area lights: ``aiExposure`` reports ``keyable=False`` but
    ``channelBox=True`` — it can be keyframed from the Channel Box, so the filter
    must not hide it (the tooltip promises "can be keyframed").
    """

    @classmethod
    def setUpClass(cls) -> None:
        from maya.api import OpenMaya as om2

        cmds = support.new_scene()
        cls.node = cmds.group(em=True, name="ChannelBoxFilterNode")
        cmds.addAttr(cls.node, longName="cbKeyableFloat", attributeType="float",
                     keyable=True)
        cmds.addAttr(cls.node, longName="cbPlainFloat", attributeType="float",
                     keyable=False)

        # addAttr has no channelBox flag (measured) - create it through the API,
        # the same way MtoA creates attributes such as aiExposure.
        selection = om2.MSelectionList()
        selection.add(cls.node)
        dep = om2.MFnDependencyNode(selection.getDependNode(0))
        numeric = om2.MFnNumericAttribute()
        attr = numeric.create("cbOnlyFloat", "cbof", om2.MFnNumericData.kFloat, 0.0)
        numeric.keyable = False
        numeric.channelBox = True
        dep.addAttribute(attr)
        cmds.flushUndo()

    def _filtered_search(self, pattern: str):
        engine = SearchEngine(AttributeScanner())
        result = SelectionManager.resolve([self.node])
        records = DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )
        return engine.search(records, pattern, SearchFilters(only_keyable=True))

    def test_channel_box_attribute_passes_the_filter(self) -> None:
        """keyable=False + channelBox=True (Arnold Exposure style) must pass."""
        found = self._filtered_search("cbOnlyFloat")
        self.assertEqual(len(found.attributes), 1)
        definition = found.attributes[0].definition
        self.assertFalse(definition.is_keyable)
        self.assertTrue(definition.is_channel_box)

    def test_keyable_attribute_still_passes(self) -> None:
        """A strictly keyable attribute keeps passing, as before."""
        found = self._filtered_search("cbKeyableFloat")
        self.assertEqual(len(found.attributes), 1)
        self.assertTrue(found.attributes[0].definition.is_keyable)

    def test_plain_attribute_is_hidden(self) -> None:
        """Neither keyable nor channelBox: the filter must keep hiding it."""
        found = self._filtered_search("cbPlainFloat")
        self.assertEqual(len(found.attributes), 0)


if __name__ == "__main__":
    unittest.main()
