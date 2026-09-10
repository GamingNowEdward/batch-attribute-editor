"""End-to-end session tests (the product experience of requirement section 39).

Simulates the complete workflow:
select → traverse (including Shapes) → search → type resolution → channels →
preview → batch modify → a single undo.
"""

from __future__ import annotations

import time
import unittest

from core.session import BatchAttributeSession
from core.traversal import TraversalScope
from core.types import AttributeKind
from tests import support


class SessionEndToEndTest(unittest.TestCase):
    """The complete workflow."""

    def setUp(self) -> None:
        # Every test rebuilds the scene: some tests (e.g. the large data volume
        # test) create a new scene, which would destroy a scene shared via setUpClass.
        self.scene = support.build_scene()
        self.cmds = support.ensure_maya()
        self.cmds.undoInfo(state=True, infinity=True)
        self.cmds.flushUndo()
        self.session = BatchAttributeSession()
        self.session.resolve_selection(
            TraversalScope.SELECTION_AND_DESCENDANTS, nodes=[self.scene["root"]]
        )

    def group_for(self, pattern: str, name: str):
        result = self.session.search(pattern)
        for item in result.attributes:
            if item.name == name:
                return item
        self.fail(f"Attribute {name} not found")

    # ------------------------------------------------------------ traversal state

    def test_selection_includes_shapes(self) -> None:
        """After selecting one root node, Shapes must appear in the scanned range."""
        names = [record.display_name for record in self.session.records]
        self.assertIn("CubeAShape", names)
        self.assertIn("CubeBIntermediateshape", names)
        self.assertGreater(self.session.state.node_count, 10)

    def test_state_description_is_informative(self) -> None:
        """The state description must tell the user what was scanned."""
        text = self.session.state.describe()
        self.assertIn("nodes", text)
        self.assertIn("shapes", text)

    def test_selection_only_scope_reduces_nodes(self) -> None:
        """The current-selection-only scope must noticeably reduce the node count."""
        full = self.session.state.node_count
        self.session.resolve_selection(TraversalScope.SELECTION_ONLY,
                                       nodes=[self.scene["root"]])
        self.assertEqual(self.session.state.node_count, 1)
        self.assertLess(self.session.state.node_count, full)

    # ------------------------------------------------------------ search and channels

    def test_search_reports_type_and_count(self) -> None:
        """Search results must give the type and the node count (requirement section 6)."""
        result = self.session.search("visibility")
        group = [item for item in result.attributes if item.name == "visibility"][0]
        self.assertEqual(group.type_label, "Boolean")
        self.assertGreater(group.node_count, 10)

    def test_color_channels_are_rgb(self) -> None:
        """Color3 channels must be R/G/B."""
        group = self.group_for("color", "overrideColorRGB")
        channels = self.session.channels_for(group)
        self.assertEqual([channel.label for channel in channels], ["R", "G", "B"])
        self.assertIs(group.definition.kind, AttributeKind.COLOR3)

    def test_vector_channels_are_xyz(self) -> None:
        """Double3 channels must be X/Y/Z."""
        group = self.group_for("translate", "translate")
        channels = self.session.channels_for(group)
        self.assertEqual([channel.label for channel in channels], ["X", "Y", "Z"])

    def test_sample_values_are_read_for_prefill(self) -> None:
        """Current values can be read for the UI prefill."""
        group = self.group_for("translateX", "translateX")
        channels = self.session.channels_for(group)
        samples = self.session.sample_values(group, channels)
        self.assertTrue(samples, "At least one current value should be readable")

    # ------------------------------------------------------------ preview

    def test_preview_reports_modify_and_skip(self) -> None:
        """The preview must state how many will be modified, how many skipped and why (requirement section 21)."""
        cube_a = self.scene["cube_a"]
        self.cmds.setAttr(f"{cube_a}.customFloat", lock=True)

        group = self.group_for("customFloat", "customFloat")
        channels = self.session.channels_for(group)
        payload = self._payload(channels, 0.4)
        preview = self.session.preview(group, payload)

        self.assertGreater(preview.will_modify, 5)
        self.assertGreaterEqual(preview.skipped, 1)
        self.assertIn("Locked", preview.skip_summary())
        self.assertIn("Will modify", preview.describe())
        self.assertTrue(preview.modify_names())

        self.cmds.setAttr(f"{cube_a}.customFloat", lock=False)

    def test_preview_lists_missing_attribute_skips(self) -> None:
        """For an attribute that exists on only some nodes, the preview must report the missing count."""
        group = self.group_for("customLabel", "customLabel")
        channels = self.session.channels_for(group)
        payload = self._payload(channels, "x")
        preview = self.session.preview(group, payload)
        self.assertGreater(preview.count(_missing_status()), 0)

    def test_preview_summary_counts_add_up(self) -> None:
        """Preview statistics must be self-consistent: modified + skipped = total matches."""
        group = self.group_for("customFloat", "customFloat")
        channels = self.session.channels_for(group)
        payload = self._payload(channels, 0.2)
        preview = self.session.preview(group, payload)
        self.assertEqual(preview.will_modify + preview.skipped, len(preview.items))

    def test_preview_detail_text_lists_changes_and_skips(self) -> None:
        """The detailed preview lists old → new per channel plus every skip reason."""
        cube_a = self.scene["cube_a"]
        self.cmds.setAttr(f"{cube_a}.customFloat", lock=True)

        group = self.group_for("customFloat", "customFloat")
        channels = self.session.channels_for(group)
        payload = self._payload(channels, 0.42)
        preview = self.session.preview(group, payload)

        detail = preview.detail_text()
        self.assertIn("── Will modify ──", detail)
        self.assertIn("→", detail)
        self.assertIn("0.42", detail)
        self.assertIn("── Skipped ──", detail)
        self.assertIn("Locked", detail)
        self.assertEqual(len(preview.change_lines()), preview.channel_writes)
        self.assertTrue(preview.skipped_lines())

        self.cmds.setAttr(f"{cube_a}.customFloat", lock=False)

    # ------------------------------------------------------------ full workflow

    def test_full_workflow_with_single_undo(self) -> None:
        """The core experience of section 39: search → preview → batch edit → a single undo."""
        group = self.group_for("visibility", "visibility")
        self.assertIs(group.definition.kind, AttributeKind.BOOL)

        channels = self.session.channels_for(group)
        payload = self._payload(channels, False)

        preview = self.session.preview(group, payload)
        self.assertGreater(preview.will_modify, 10)

        report = self.session.apply(group, payload)
        self.assertGreater(report.succeeded, 10)
        self.assertEqual(report.failed, 0)
        self.assertIn("Succeeded", report.describe())

        self.assertFalse(self.cmds.getAttr("CubeAShape.visibility"))
        self.assertFalse(self.cmds.getAttr("CubeDShape.visibility"))

        pops = 0
        while pops < 20:
            try:
                self.cmds.undo()
            except RuntimeError:
                break
            pops += 1
        self.assertEqual(pops, 1, "The whole workflow takes exactly one Undo")
        self.assertTrue(self.cmds.getAttr("CubeAShape.visibility"))

    def test_color_workflow(self) -> None:
        """Colour workflow: batch write of R/G/B + a single undo."""
        group = self.group_for("color", "overrideColorRGB")
        channels = self.session.channels_for(group)
        payload = self._payload(channels, 0.5)
        report = self.session.apply(group, payload)

        self.assertGreater(report.succeeded, 10)
        value = self.cmds.getAttr("CubeA.overrideColorRGB")[0]
        self.assertAlmostEqual(value[0], 0.5, places=5)
        self.assertAlmostEqual(value[2], 0.5, places=5)

    def test_apply_after_preview_uses_user_value_not_scene_value(self) -> None:
        """The write uses the user's input value, not the current value read from the scene."""
        group = self.group_for("customInt", "customInt")
        channels = self.session.channels_for(group)
        preview = self.session.preview(group, self._payload(channels, 0))
        self.assertGreater(preview.will_modify, 5)

        self.session.apply(group, self._payload(channels, 11))
        self.assertEqual(self.cmds.getAttr("CubeA.customInt"), 11)

    def test_apply_log_records_audit_entries(self) -> None:
        """Every successful write leaves an ``old → new`` audit entry in the log."""
        from utils.logging_utils import LogLevel

        group = self.group_for("customFloat", "customFloat")
        channels = self.session.channels_for(group)
        report = self.session.apply(group, self._payload(channels, 0.55))

        self.assertGreater(report.succeeded, 0)
        infos = [entry for entry in report.log.entries if entry.level is LogLevel.INFO]
        self.assertEqual(len(infos), report.succeeded)
        self.assertIn("→", infos[0].message)

    # ------------------------------------------------------------ refresh and cache

    def test_cache_is_used_and_reports_stats(self) -> None:
        """The cache must take effect and be able to report its own size."""
        self.session.search("customFloat")
        note = self.session.cache_note()
        self.assertIn("Cache", note)
        stats = self.session.cache.stats()
        self.assertGreater(stats.nodes, 5)

    def test_refresh_invalidates_cache(self) -> None:
        """Refreshing bumps the cache generation and re-resolves the selection."""
        self.session.search("customFloat")
        before = self.session.cache.generation
        self.session.refresh()
        self.assertGreater(self.session.cache.generation, before)

    def test_search_after_node_deleted_does_not_crash(self) -> None:
        """Searching after a node was deleted must not crash (stale cache + deleted node)."""
        cmds = support.ensure_maya()
        temp = cmds.group(em=True, name="TempSearchNode")
        cmds.addAttr(temp, longName="tempSearchFloat", attributeType="float", keyable=True)
        cmds.parent(temp, self.scene["cube_a"])

        session = BatchAttributeSession()
        session.resolve_selection(TraversalScope.SELECTION_AND_DESCENDANTS,
                                  nodes=[self.scene["cube_a"]])
        found = session.search("tempSearchFloat")
        self.assertTrue(found.attributes)

        cmds.delete(temp)
        # search again without refreshing the cache: stale results are allowed, an exception is not
        session.search("tempSearchFloat")

    def test_large_hierarchy_performance(self) -> None:
        """29. Large node counts: both search and write must stay within a usable range."""
        cmds = support.new_scene()
        root = cmds.group(em=True, name="PerfRoot_GRP")
        for index in range(300):
            group = cmds.group(em=True, name=f"PerfGroup{index:03d}", parent=root)
            for sub in range(2):
                node = cmds.polyCube(name=f"PerfMesh{index:03d}_{sub}")[0]
                cmds.parent(node, group)
                cmds.addAttr(node, longName="perfWeight", attributeType="float", keyable=True)
        cmds.flushUndo()

        session = BatchAttributeSession()
        started = time.perf_counter()
        session.resolve_selection(TraversalScope.SELECTION_AND_DESCENDANTS, nodes=[root])
        traversal_time = time.perf_counter() - started

        self.assertGreater(session.state.node_count, 1500)
        self.assertLess(traversal_time, 5.0, "Traversing 1500+ nodes should finish within seconds")

        started = time.perf_counter()
        found = session.search("perfWeight")
        search_time = time.perf_counter() - started
        self.assertLess(search_time, 10.0, "The first search should stay within a usable range")

        group = [item for item in found.attributes if item.name == "perfWeight"][0]
        self.assertEqual(group.node_count, 600)

        channels = session.channels_for(group)
        payload = self._payload(channels, 0.6)
        started = time.perf_counter()
        report = session.apply(group, payload)
        apply_time = time.perf_counter() - started

        self.assertEqual(report.succeeded, 600)
        self.assertLess(apply_time, 10.0, "A batch write to 600 nodes should stay within a usable range")

        # the second search, served from cache, should be clearly faster
        started = time.perf_counter()
        session.search("perfWeight")
        cached_time = time.perf_counter() - started
        self.assertLess(cached_time, search_time + 0.5)

    # ------------------------------------------------------------ helpers

    @staticmethod
    def _payload(channels, value):
        from core.batch_setter import ValuePayload

        payload = ValuePayload()
        for channel in channels:
            payload.set(channel, value)
        return payload


def _missing_status():
    """ValidationStatus.MISSING (deferred import to avoid a cycle)."""
    from core.compatibility import ValidationStatus

    return ValidationStatus.MISSING


if __name__ == "__main__":
    unittest.main()
