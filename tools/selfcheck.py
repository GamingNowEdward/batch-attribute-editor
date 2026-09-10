"""Self-check script that runs inside a real Maya session.

Usage (Maya's Script Editor, Python tab)::

    import sys
    sys.path.insert(0, r"C:\\opencode\\BatchAttributeEditor")
    import tools.selfcheck as selfcheck
    selfcheck.run(create_test_nodes=True)

It will:

1. verify that all modules import under the **current Maya version**
   (including the Qt version branch);
2. build the main window (this step can only be verified in a real GUI session);
3. optionally build a temporary hierarchy and run the full
   "traverse -> search -> type resolution -> preview -> batch modify -> single undo"
   pipeline;
4. print the result to the Script Editor and delete the temporary nodes at the end.

By default it creates **no** nodes and does **not** modify the current scene; only
an explicit ``create_test_nodes=True`` builds a temporary hierarchy, and it is
deleted once used.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

#: Flat structure: the parent of tools/ is the project root, which must be on sys.path to import core / ui
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)


def _log(lines: List[str], text: str, ok: Optional[bool] = None) -> None:
    prefix = "" if ok is None else ("[ok]   " if ok else "[FAIL] ")
    lines.append(prefix + text)
    print(prefix + text)


def run(create_test_nodes: bool = False, show_window: bool = False) -> bool:
    """Run the self-check. Returns whether everything passed."""
    from maya import cmds

    if not hasattr(cmds, "about"):
        # importing maya.cmds outside Maya (or before standalone initialization) yields an empty module
        print("[Batch Attribute Editor] Maya is not initialised yet. "
              "Run this script from Maya's Script Editor (or call maya.standalone.initialize() first).")
        return False

    lines: List[str] = []
    failures = 0

    _log(lines, f"Maya {cmds.about(version=True)} · Qt {cmds.about(qtVersion=True)} "
                f"· batch={cmds.about(batch=True)}")

    # ---------------------------------------------------------------- imports
    modules = (
        "__init__",
        "main",
        "core.session",
        "ui.qt",
        "ui.styles",
        "ui.attribute_model",
        "ui.panels",
        "ui.editors.base",
        "ui.editors.channel_widgets",
        "ui.editors.value_editors",
        "ui.editors.factory",
        "ui.main_window",
    )
    for name in modules:
        try:
            __import__(name)
            _log(lines, f"import {name}", True)
        except Exception as exc:  # noqa: BLE001
            failures += 1
            _log(lines, f"import {name} → {type(exc).__name__}: {exc}", False)

    from ui.qt import QT_API

    _log(lines, f"Qt binding: {QT_API}")

    # ---------------------------------------------------------------- window
    window = None
    if not cmds.about(batch=True):
        try:
            from ui.main_window import BatchAttributeEditorWindow

            window = BatchAttributeEditorWindow()
            _log(lines, "Main window constructed", True)
            _log(lines, f"  Nodes scanned: {window.session.state.node_count}"
                        f" ({window.session.state.selection_note})")
            if show_window:
                window.show(dockable=True, floating=True)
                _log(lines, "Window shown")
        except Exception as exc:  # noqa: BLE001
            failures += 1
            import traceback

            _log(lines, f"Construct main window → {type(exc).__name__}: {exc}", False)
            print(traceback.format_exc())
    else:
        _log(lines, "batch mode: skipping window construction (a QApplication cannot be created under standalone)")

    # ---------------------------------------------------------------- full pipeline
    if create_test_nodes:
        failures += _run_pipeline(lines)

    if window is not None:
        try:
            window.teardown()
            window.deleteLater()
        except Exception:  # noqa: BLE001
            pass

    print("\n===== Batch Attribute Editor self-check result =====")
    print("All checks passed" if not failures else f"{failures} check(s) failed")
    return failures == 0


def _run_pipeline(lines: List[str]) -> int:
    """Build a temporary hierarchy and run the full pipeline. Returns the failure count."""
    from maya import cmds

    from core.session import BatchAttributeSession
    from core.traversal import TraversalScope

    failures = 0
    root = cmds.group(em=True, name="BAE_SelfCheck_GRP")
    try:
        for index in range(4):
            node = cmds.polyCube(name=f"BAE_SelfCheck_Mesh{index}")[0]
            cmds.parent(node, root)
            cmds.addAttr(node, longName="baeWeight", attributeType="float", keyable=True)
        cmds.select(root, replace=True)

        session = BatchAttributeSession()
        session.resolve_selection(TraversalScope.SELECTION_AND_DESCENDANTS, nodes=[root])
        shapes = [record for record in session.records if record.is_shape]
        _log(lines, f"Traversal: {session.state.node_count} nodes, {len(shapes)} of them shapes",
             bool(shapes))

        found = session.search("baeWeight")
        group = next((item for item in found.attributes if item.name == "baeWeight"), None)
        if group is None:
            _log(lines, "Search for baeWeight failed", False)
            return failures + 1
        _log(lines, f"Search: {group.name} · {group.type_label} · {group.node_count} nodes", True)

        channels = session.channels_for(group)
        from core.batch_setter import ValuePayload

        payload = ValuePayload()
        for channel in channels:
            payload.set(channel, 0.42)

        preview = session.preview(group, payload)
        _log(lines, f"Preview: {preview.describe().splitlines()[0]}", preview.will_modify > 0)

        cmds.flushUndo()
        report = session.apply(group, payload)
        _log(lines, f"Apply: {report.describe()}", report.succeeded == group.node_count)

        value = cmds.getAttr(f"{cmds.ls(root, long=True)[0]}|BAE_SelfCheck_Mesh0.baeWeight")
        _log(lines, f"Write check: baeWeight = {value}", abs(value - 0.42) < 1e-5)

        pops = 0
        while pops < 10:
            try:
                cmds.undo()
            except RuntimeError:
                break
            pops += 1
        _log(lines, f"Undo: the batch of {report.succeeded} writes took {pops} Undo", pops == 1)
        if pops != 1:
            failures += 1
    finally:
        if cmds.objExists(root):
            cmds.delete(root)
    return failures


if __name__ == "__main__":
    run(create_test_nodes=True)
