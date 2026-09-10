"""Helper tool scripts (run inside Maya).

``selfcheck.py`` - verifies in a real Maya session that the tool can be
imported and that the window can be built, and optionally runs the full
"traverse -> search -> preview -> batch modify -> single undo" pipeline on
temporary nodes.
"""

from __future__ import annotations

__all__ = ["selfcheck"]
