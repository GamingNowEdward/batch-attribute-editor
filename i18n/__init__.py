"""Lightweight localization for the Batch Attribute Editor.

Public API::

    from i18n import tr, plural, set_language, get_language

    tr("button.apply")                       # "Apply" / "应用"
    tr("results.empty_no_match", count=7)    # "No attribute matches (scanned 7 nodes)"
    plural(count, "node")                    # "2 nodes" / "2 个节点"

The package is pure Python so that both ``core`` and ``ui`` can depend on it.
English is the reference language; a missing entry always falls back to
English, and a missing key never raises.
"""

from __future__ import annotations

from i18n.manager import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    TranslationManager,
    get_language,
    manager,
    normalize_language,
    plural,
    set_language,
    tr,
)

__all__ = [
    "DEFAULT_LANGUAGE",
    "SUPPORTED_LANGUAGES",
    "TranslationManager",
    "get_language",
    "manager",
    "normalize_language",
    "plural",
    "set_language",
    "tr",
]
