"""Undo Chunk management: one batch Apply corresponds to one Maya Undo.

Measured evidence (Maya 2024 / mayapy):

* Writes via ``MPlug.setFloat/setInt/...`` do **not enter** the Undo queue
  (after 5 consecutive writes, ``cmds.undo()`` fails immediately, pops=0).
* Every write via ``cmds.setAttr`` is one Undo entry (5 writes = 5 undos).
* When ``cmds.setAttr`` is wrapped in ``undoInfo(openChunk/closeChunk)``, the
  **whole block occupies only 1 Undo**
  (measured: 50 writes -> pops=1; a failing write inside the chunk still counts as 1 undo).

Therefore batch writes must go through the chunk provided by :class:`UndoManager`.

Another measured conclusion: ``undoInfo(closeChunk=True)`` **succeeds silently**
when no chunk is open (it does not raise). So never write "loop closeChunk until it
raises" drain logic, since that would hang the Maya main thread. This module uses an
explicit state flag instead.
"""

from __future__ import annotations

from types import TracebackType
from typing import Optional, Type

from i18n import tr
from utils.logging_utils import describe_exception, OperationLog

DEFAULT_CHUNK_NAME = "Batch Attribute Editor"


class UndoManager:
    """Manage the lifetime of one Undo Chunk.

    Usage::

        with UndoManager("Set visibility") as undo:
            ...batch writes...

    The chunk is opened on entry and closed on exit; it is closed correctly even
    if an exception is raised inside the block, which guarantees that writes that
    already completed still occupy only one Undo.
    """

    def __init__(self, name: str = DEFAULT_CHUNK_NAME, log: Optional[OperationLog] = None) -> None:
        self.name = name
        self.log = log
        self._opened = False

    # ------------------------------------------------------------ context protocol

    def __enter__(self) -> "UndoManager":
        self.open()
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc: Optional[BaseException],
                 traceback: Optional[TracebackType]) -> bool:
        self.close()
        return False  # do not swallow exceptions

    # ------------------------------------------------------------ open / close

    def open(self) -> bool:
        """Open the Undo Chunk; on failure record a log entry and return False.

        It does not raise, so the whole batch is not aborted.
        """
        if self._opened:
            return True
        from maya import cmds

        try:
            cmds.undoInfo(openChunk=True, chunkName=self.name)
        except RuntimeError as exc:
            self._record(tr("log.undo_open_failed", error=describe_exception(exc)))
            return False
        self._opened = True
        return True

    def close(self) -> None:
        """Close the Undo Chunk.

        Only close it when it was actually opened; Maya silently succeeds on a
        redundant closeChunk, but we still track the state explicitly so that we
        do not interfere with external chunks.
        """
        if not self._opened:
            return
        from maya import cmds

        try:
            cmds.undoInfo(closeChunk=True)
        except RuntimeError as exc:
            self._record(tr("log.undo_close_failed", error=describe_exception(exc)))
        finally:
            self._opened = False

    @property
    def is_open(self) -> bool:
        return self._opened

    def _record(self, message: str) -> None:
        if self.log is not None:
            self.log.warning(message)

    # ------------------------------------------------------------ queries

    @staticmethod
    def enabled() -> bool:
        """Whether Maya's Undo is currently enabled."""
        from maya import cmds

        try:
            return bool(cmds.undoInfo(query=True, state=True))
        except RuntimeError:
            return False

    @staticmethod
    def flush() -> None:
        """Flush the Undo queue (for tests; not needed in the normal flow)."""
        from maya import cmds

        try:
            cmds.flushUndo()
        except RuntimeError:
            pass

    @staticmethod
    def undo() -> bool:
        """Perform one undo; return False when there is nothing to undo."""
        from maya import cmds

        try:
            cmds.undo()
            return True
        except RuntimeError:
            return False

    @staticmethod
    def redo() -> bool:
        """Perform one redo; return False when there is nothing to redo."""
        from maya import cmds

        try:
            cmds.redo()
            return True
        except RuntimeError:
            return False
