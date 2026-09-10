"""Batch Attribute Editor entry point.

Run this in Maya's Script Editor::

    import sys
    sys.path.insert(0, r"C:\\opencode\\BatchAttributeEditor")
    import main
    main.launch()

It can also be turned into a shelf button or an auto-load in userSetup.py.
"""

from __future__ import annotations

import sys
from typing import List, Optional

import bootstrap

__version__ = "1.0.0"

#: Keep the current window at module level so reopening can reclaim the scriptJob correctly
_WINDOW = None


def launch(dock: bool = False, restore: bool = False,
           release_conflicts: bool = True) -> object:
    """Open the Batch Attribute Editor.

    :param dock: ``True`` docks it to the right panel; ``False`` (the default)
        opens it as a floating window. A floating window can be dragged and
        docked as well, which makes it the safest default.
    :param restore: used by workspace restore; reuses an already existing window.
    :param release_conflicts: under the flat structure names like ``core`` /
        ``ui`` / ``utils`` are very common; if a module with the same name from
        another plug-in already exists, it is evicted from ``sys.modules`` by
        default (otherwise ``import core.session`` picks up the wrong module).
        Set to ``False`` to disable.
    """
    from maya import cmds

    global _WINDOW

    bootstrap.ensure_on_path()
    _resolve_module_conflicts(release_conflicts)

    if restore and _WINDOW is not None:
        return _WINDOW

    _close_previous()

    from ui.main_window import (
        WORKSPACE_CONTROL_NAME,
        BatchAttributeEditorWindow,
    )

    if cmds.workspaceControl(WORKSPACE_CONTROL_NAME, exists=True):
        cmds.deleteUI(WORKSPACE_CONTROL_NAME)

    window = BatchAttributeEditorWindow()
    _WINDOW = window

    try:
        window.show(dockable=True, floating=True)
        if dock:
            cmds.workspaceControl(
                WORKSPACE_CONTROL_NAME, edit=True, dockToMainWindow=("right", False)
            )
    except (TypeError, RuntimeError) as exc:
        # non-Maya environments (e.g. pure Qt smoke tests) do not accept the dockable argument
        print(f"[Batch Attribute Editor] Problem showing the window: {exc}")
        window.show()

    return window


def close() -> None:
    """Close the window and clean up the scriptJob it registered."""
    global _WINDOW
    window, _WINDOW = _WINDOW, None
    if window is None:
        return

    try:
        window.teardown()
    except Exception:  # noqa: BLE001 - teardown must not raise
        pass

    try:
        from maya import cmds

        from ui.main_window import WORKSPACE_CONTROL_NAME

        window.close()
        if cmds.workspaceControl(WORKSPACE_CONTROL_NAME, exists=True):
            cmds.deleteUI(WORKSPACE_CONTROL_NAME)
    except Exception:  # noqa: BLE001
        pass


def _close_previous() -> None:
    """Reclaim the window and scriptJob left behind by the previous open."""
    global _WINDOW

    if _WINDOW is not None:
        close()
        return

    # fallback for when the module was reloaded and the module-level reference was
    # lost: scan for leftover scriptJobs
    _kill_orphan_jobs()


def _kill_orphan_jobs() -> None:
    """Clean up scriptJobs pointing at windows that no longer exist, avoiding double firing."""
    from maya import cmds

    try:
        jobs: List[str] = cmds.scriptJob(listJobs=True) or []
    except RuntimeError:
        return

    for entry in jobs:
        if "BatchAttributeEditorWindow" not in entry and "_on_scene_event" not in entry:
            continue
        try:
            job_id = int(str(entry).split(":", 1)[0].strip())
        except (ValueError, IndexError):
            continue
        try:
            if cmds.scriptJob(exists=job_id):
                cmds.scriptJob(kill=job_id, force=True)
        except (RuntimeError, TypeError):
            continue


def reload_and_launch(dock: bool = False) -> object:
    """For development: reload **this project's** modules and then open the window.

    Only the top-level modules claimed by this project are handled (see
    ``bootstrap.TOP_LEVEL_MODULES``), and only modules that really live under
    this project directory are removed - modules of other plug-ins or of Maya
    itself are never touched.
    """
    import importlib
    import os

    close()
    root = bootstrap.project_root()

    names: List[str] = []
    for name, module in list(sys.modules.items()):
        if name.split(".", 1)[0] not in bootstrap.TOP_LEVEL_MODULES:
            continue
        path = getattr(module, "__file__", None)
        if path and not os.path.abspath(path).startswith(root):
            continue  # someone else's module with the same name: leave it alone
        names.append(name)

    # remove from the deepest submodule upwards; the following import rebuilds the whole module tree
    for name in sorted(names, key=lambda item: item.count("."), reverse=True):
        sys.modules.pop(name, None)

    bootstrap.ensure_on_path()
    importlib.invalidate_caches()
    importlib.import_module("main")
    return launch(dock=dock)


def _resolve_module_conflicts(release: bool) -> None:
    """Handle top-level modules that clash with other plug-ins (the cost of the flat structure).

    Without this, ``import core.session`` may pick up another plug-in's ``core``
    and the tool fails in ways that are hard to diagnose. Conflicts are reported
    to the user explicitly here.
    """
    if not release:
        return
    conflicts = bootstrap.release_conflicting_modules()
    if conflicts:
        print("[Batch Attribute Editor] Conflicting module names detected, taken over: "
              + bootstrap.describe_conflicts(conflicts))


__all__ = ["__version__", "close", "launch", "reload_and_launch"]
