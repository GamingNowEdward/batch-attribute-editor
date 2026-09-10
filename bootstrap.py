"""Bootstrap layer: sys.path injection and top-level module name conflict handling.

The project uses a **flat structure** (``core`` / ``ui`` / ``utils`` / ``tests`` /
``main`` sit directly in the project root); the benefit is that it matches the
convention of Maya's script directories and can be dropped straight into
``Documents/maya/<version>/scripts/``.

The cost is that these top-level names are very common and may clash with other
plug-ins. This module is responsible for:

1. adding the project root to ``sys.path`` (idempotent);
2. **detecting** foreign modules with the same name and, when needed, evicting
   them from ``sys.modules`` instead of letting ``import core.session`` silently
   pick up someone else's ``core``.

Detection and release are two separate functions; callers can detect without
releasing.
"""

from __future__ import annotations

import os
import sys
from typing import List, Tuple

#: Top-level module names claimed by this project
TOP_LEVEL_MODULES: Tuple[str, ...] = ("core", "ui", "utils", "tests", "main", "bootstrap")


def project_root() -> str:
    """Absolute path of the project root directory."""
    return os.path.dirname(os.path.abspath(__file__))


def ensure_on_path() -> str:
    """Add the project root to ``sys.path`` (idempotent) and return the project root."""
    root = project_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    return root


def conflicting_modules() -> List[Tuple[str, str]]:
    """Find top-level module names already claimed by **another source**.

    Returns ``[(module name, file path of that module), ...]``.
    Only modules that really come from outside this project are reported.
    """
    root = project_root()
    conflicts: List[Tuple[str, str]] = []
    for name in TOP_LEVEL_MODULES:
        module = sys.modules.get(name)
        if module is None:
            continue
        path = getattr(module, "__file__", None)
        if not path:
            # namespace packages and the like have no __file__: decide from __path__
            paths = list(getattr(module, "__path__", []) or [])
            if paths and any(os.path.abspath(item).startswith(root) for item in paths):
                continue
            if paths:
                conflicts.append((name, paths[0]))
            continue
        if not os.path.abspath(path).startswith(root):
            conflicts.append((name, os.path.abspath(path)))
    return conflicts


def release_conflicting_modules() -> List[Tuple[str, str]]:
    """Remove foreign same-name modules from ``sys.modules`` and return the removed list.

    A necessary cost of the flat structure: without this, ``import core.session``
    picks up another plug-in's ``core`` and the tool fails in ways that are hard
    to diagnose. Callers should print the return value for the user.
    """
    conflicts = conflicting_modules()
    for name, _path in conflicts:
        sys.modules.pop(name, None)
    return conflicts


def describe_conflicts(conflicts: List[Tuple[str, str]]) -> str:
    """Format the conflict list as one readable line."""
    return ", ".join(f"{name} (from {path})" for name, path in conflicts)
