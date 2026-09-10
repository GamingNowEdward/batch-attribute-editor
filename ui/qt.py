"""Qt compatibility layer: PySide6 first, PySide2 as fallback.

Measured environment: the mayapy site-packages of Maya 2024.2 only ship
**PySide2 5.15.2**, while a GUI session may provide PySide6. UI code imports only this
module and never imports PySide* directly.

The real differences between the two versions (they must be handled or ImportError):

* ``QAction`` lives in ``QtWidgets`` in PySide2 and in ``QtGui`` in PySide6.
* Dialogs and drag-and-drop use ``exec()`` (PySide6 removed ``exec_()``).
* The ``shiboken`` package name differs (``shiboken6`` / ``shiboken2``).
"""

from __future__ import annotations

QT_API = ""

try:  # pragma: no cover - depends on the runtime environment
    from PySide6 import QtCore, QtGui, QtWidgets  # type: ignore
    from PySide6.QtCore import Signal, Slot  # type: ignore

    QT_API = "PySide6"
except ImportError:  # pragma: no cover
    try:
        from PySide2 import QtCore, QtGui, QtWidgets  # type: ignore
        from PySide2.QtCore import Signal, Slot  # type: ignore

        QT_API = "PySide2"
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Batch Attribute Editor requires PySide6 or PySide2 "
            "(Maya ships one of the two)"
        ) from exc


#: The location of QAction changes with the version
QAction = getattr(QtGui, "QAction", None) or getattr(QtWidgets, "QAction")

Qt = QtCore.Qt
QSignalBlocker = QtCore.QSignalBlocker


def wrap_maya_pointer(pointer):  # pragma: no cover - needs the Maya GUI
    """Wrap Maya's C++ pointer as a Qt object."""
    try:
        from shiboken6 import wrapInstance  # type: ignore
    except ImportError:
        from shiboken2 import wrapInstance  # type: ignore

    return wrapInstance(int(pointer))


def maya_main_window():  # pragma: no cover - needs the Maya GUI
    """Maya main window (used as the dialog parent so modality behaves correctly)."""
    from maya import OpenMayaUI as omui

    pointer = omui.MQtUtil.mainWindow()
    return wrap_maya_pointer(pointer) if pointer else None


def exec_dialog(dialog) -> int:  # pragma: no cover - needs Qt
    """Execute a dialog compatibly with PySide2/PySide6."""
    if hasattr(dialog, "exec"):
        return dialog.exec()
    return dialog.exec_()


__all__ = [
    "QAction",
    "QT_API",
    "QSignalBlocker",
    "Qt",
    "QtCore",
    "QtGui",
    "QtWidgets",
    "Signal",
    "Slot",
    "exec_dialog",
    "maya_main_window",
    "wrap_maya_pointer",
]
