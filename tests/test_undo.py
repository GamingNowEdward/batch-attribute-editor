"""Undo / Redo tests (requirement sections 23, 35 items 23-24) - a hard requirement for a production tool.

One batch Apply must correspond to **one** Maya Undo, not one per node.

Note on counting: ``undoInfo(query=True, length=True)`` returns the queue
**capacity**, not the number of entries (measured: it is always constant), so
these tests count real entries by "undo repeatedly until it raises".
"""

from __future__ import annotations

import unittest

from core.attributes import AttributeScanner
from core.batch_setter import BatchSetter, ValuePayload
from core.search import SearchEngine
from core.selection import SelectionManager
from core.session import BatchAttributeSession
from core.traversal import DagTraversal, TraversalScope
from core.undo import UndoManager
from tests import support


class UndoTest(unittest.TestCase):
    """Undo behaviour of batch modifications."""

    def setUp(self) -> None:
        self.scene = support.build_scene()
        self.cmds = support.ensure_maya()
        self.cmds.undoInfo(state=True, infinity=True)
        self.cmds.flushUndo()
        self.setter = BatchSetter()

    def count_undo_pops(self, limit: int = 100) -> int:
        """Undo repeatedly until there is nothing left, and return the real number of undo entries."""
        pops = 0
        while pops < limit:
            try:
                self.cmds.undo()
            except RuntimeError:
                break
            pops += 1
        return pops

    def make_group(self, attribute: str, pattern: str = ""):
        """Search out the aggregated row of the target attribute."""
        result = SelectionManager.resolve([self.scene["root"]])
        records = DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )
        engine = SearchEngine(AttributeScanner())
        found = engine.search(records, pattern or attribute)
        for item in found.attributes:
            if item.name == attribute:
                session = BatchAttributeSession()
                session.records = records
                return item, session.channels_for(item)
        self.fail(f"Attribute {attribute} not found")

    def test_single_apply_is_single_undo(self) -> None:
        """23. One Apply (multiple nodes) takes exactly one Undo."""
        group, channels = self.make_group("customFloat")
        payload = ValuePayload()
        for channel in channels:
            payload.set(channel, 0.5)

        report = self.setter.apply(group, payload)
        self.assertGreater(report.succeeded, 5, "Multiple nodes should be modified")
        self.assertEqual(self.cmds.getAttr("CubeA.customFloat"), 0.5)

        pops = self.count_undo_pops()
        self.assertEqual(pops, 1, "The whole batch must take exactly one Undo")
        self.assertEqual(self.cmds.getAttr("CubeA.customFloat"), 0.0, "The default value should be restored after undo")

    def test_undo_restores_all_nodes(self) -> None:
        """Undo must restore **every** node that was modified."""
        group, channels = self.make_group("customInt")
        payload = ValuePayload()
        for channel in channels:
            payload.set(channel, 5)
        self.setter.apply(group, payload)

        targets = ["CubeA", "CubeB", "CubeC", "CubeD", "LocA"]
        for name in targets:
            self.assertEqual(self.cmds.getAttr(f"{name}.customInt"), 5)

        self.count_undo_pops()
        for name in targets:
            self.assertEqual(self.cmds.getAttr(f"{name}.customInt"), 0,
                             f"{name}.customInt should be restored")

    def test_redo_reapplies_batch(self) -> None:
        """24. Redo must re-apply the whole batch."""
        group, channels = self.make_group("customFloat")
        payload = ValuePayload()
        for channel in channels:
            payload.set(channel, 0.25)
        self.setter.apply(group, payload)
        self.count_undo_pops()
        self.assertEqual(self.cmds.getAttr("CubeA.customFloat"), 0.0)

        self.cmds.redo()
        self.assertEqual(self.cmds.getAttr("CubeA.customFloat"), 0.25,
                         "Redo should restore the result of the batch modification")

    def test_manually_unchunked_writes_would_take_many_undos(self) -> None:
        """Control group: without an Undo Chunk, the writes take several Undo entries.

        This test proves the UndoManager chunk is necessary, not decorative.
        """
        for index in range(5):
            self.cmds.setAttr("CubeA.customFloat", float(index))
        pops = self.count_undo_pops()
        self.assertEqual(pops, 5, "Without a chunk each write takes its own Undo")

    def test_partial_failure_still_single_undo(self) -> None:
        """When the chunk contains a failed write, the successful part is still undone as one chunk."""
        self.cmds.setAttr("CubeA.customFloat", lock=True)
        # the lock itself takes one Undo entry; clear it first so the Apply entry count is exact
        self.cmds.flushUndo()

        group, channels = self.make_group("customFloat")
        payload = ValuePayload()
        for channel in channels:
            payload.set(channel, 0.9)
        report = self.setter.apply(group, payload)
        self.assertGreater(report.succeeded, 5)

        pops = self.count_undo_pops()
        self.assertEqual(pops, 1, "A batch containing skipped items still takes exactly one Undo")
        self.assertEqual(self.cmds.getAttr("CubeB.customFloat"), 0.0)

    def test_large_batch_is_single_undo(self) -> None:
        """22. Large node counts: a single Undo still holds."""
        cmds = support.new_scene()
        root = cmds.group(em=True, name="LargeRoot_GRP")
        for index in range(150):
            node = cmds.group(em=True, name=f"Large{index:03d}")
            cmds.parent(node, root)
            cmds.addAttr(node, longName="bulkFloat", attributeType="float", keyable=True)
        cmds.flushUndo()

        result = SelectionManager.resolve([root])
        records = DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )
        engine = SearchEngine(AttributeScanner())
        found = engine.search(records, "bulkFloat")
        group = [item for item in found.attributes if item.name == "bulkFloat"][0]
        self.assertEqual(group.node_count, 150)

        session = BatchAttributeSession()
        session.records = records
        channels = session.channels_for(group)
        payload = ValuePayload()
        for channel in channels:
            payload.set(channel, 0.33)

        report = self.setter.apply(group, payload)
        self.assertEqual(report.succeeded, 150)

        pops = self.count_undo_pops()
        self.assertEqual(pops, 1, "150 nodes must still take exactly one Undo")
        self.assertEqual(cmds.getAttr("Large000.bulkFloat"), 0.0)

    def test_chunk_manager_closes_without_exception(self) -> None:
        """The UndoManager chunk must open and close normally (no exceptions used for control flow)."""
        manager = UndoManager("test chunk")
        self.assertTrue(manager.open())
        self.cmds.setAttr("CubeA.customFloat", 1.0)
        manager.close()
        self.assertFalse(manager.is_open)

        manager.close()  # closing twice must be safe
        pops = self.count_undo_pops()
        self.assertEqual(pops, 1)

    def test_undo_manager_state_helpers(self) -> None:
        """The enabled / undo / redo helper methods."""
        self.assertTrue(UndoManager.enabled())
        self.cmds.setAttr("CubeA.customFloat", 2.0)
        self.assertTrue(UndoManager.undo())
        self.assertEqual(self.cmds.getAttr("CubeA.customFloat"), 0.0)
        self.assertTrue(UndoManager.redo())
        self.assertEqual(self.cmds.getAttr("CubeA.customFloat"), 2.0)


if __name__ == "__main__":
    unittest.main()
