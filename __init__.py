"""Batch Attribute Editor — batch attribute discovery and editing system for Maya.

The project uses a **flat structure**: ``core`` / ``ui`` / ``utils`` / ``tests``
sit directly in the project root, so it can be dropped straight into
``Documents/maya/<version>/scripts/``.

Two equivalent entry points:

**Entry point 1 (recommended) — use the project root directly**::

    import sys
    sys.path.insert(0, r"C:\\opencode\\BatchAttributeEditor")
    import main
    main.launch()

**Entry point 2 — treat the project root as a package**::

    import sys
    sys.path.insert(0, r"C:\\opencode")
    import BatchAttributeEditor
    BatchAttributeEditor.launch()

This module does only two things: add the project root to ``sys.path`` and then
forward to :mod:`main`.

See ``docs/ARCHITECTURE.md`` for the architecture; the Core layer does not depend on
Qt and can be tested standalone under mayapy::

    mayapy tests/run_tests.py
"""

from __future__ import annotations

import bootstrap

#: Project root added to sys.path (idempotent)
ROOT = bootstrap.ensure_on_path()

from main import __version__, close, launch, reload_and_launch  # noqa: E402

__all__ = [
    "ROOT",
    "__version__",
    "bootstrap",
    "close",
    "launch",
    "reload_and_launch",
]
