"""UI layer: Maya is only accessed through the Core session object.

``main_window`` is not imported during package initialisation — it needs the Maya GUI
(``maya.app.general.mayaMixin``), while ``panels`` / ``editors`` only need Qt, which makes
them easier to inspect on their own.
"""

from __future__ import annotations

__all__ = ["qt", "styles"]
