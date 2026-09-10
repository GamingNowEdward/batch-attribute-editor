"""Search-result table model.

Only "cheap" information is shown (attribute name, type, number of nodes involved,
number of other types sharing the name). Statistics such as Locked / Connected / Missing
that require per-node validation are computed on demand in the Details area instead, so
the first search result is still fast in scenes with 10000+ nodes.
"""

from __future__ import annotations

from typing import List, Optional, Sequence

from core.search import AggregatedAttribute
from ui.qt import QtCore, QtGui, Qt
from ui.styles import WARNING


class AttributeTableModel(QtCore.QAbstractTableModel):
    """Result model with one row per "attribute + type" pair."""

    HEADERS = ("Attribute", "Type", "Nodes", "Other types")

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._attributes: List[AggregatedAttribute] = []

    # ------------------------------------------------------------ Qt interface

    def rowCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._attributes)

    def columnCount(self, parent=QtCore.QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self.HEADERS)

    def headerData(self, section: int, orientation, role=Qt.DisplayRole):  # noqa: N802
        if orientation != Qt.Horizontal:
            return None
        if role == Qt.DisplayRole:
            if 0 <= section < len(self.HEADERS):
                return self.HEADERS[section]
            return None
        if role == Qt.TextAlignmentRole:
            # The numeric columns align right, exactly like their cells.
            if section >= 2:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)
        return None

    def data(self, index: QtCore.QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        attribute = self.attribute_at(index.row())
        if attribute is None:
            return None
        column = index.column()

        if role == Qt.DisplayRole:
            if column == 0:
                return attribute.display_name
            if column == 1:
                return attribute.type_label
            if column == 2:
                return attribute.node_count
            if column == 3:
                return attribute.other_type_total or ""
            return None

        if role == Qt.ToolTipRole:
            lines = [
                f"Long name: {attribute.name}",
                f"Short name: {attribute.short_name}",
                f"Type: {attribute.type_label}",
                attribute.definition.describe(),
                f"Nodes involved: {attribute.node_count}",
            ]
            if attribute.other_type_total:
                other_types = ", ".join(
                    f"{label} × {count}" for label, count in attribute.other_types.items()
                )
                lines.append("Nodes with the same name but a different type: " + other_types)
            return "\n".join(lines)

        if role == Qt.TextAlignmentRole and column >= 2:
            return int(Qt.AlignRight | Qt.AlignVCenter)

        if role == Qt.ForegroundRole and column == 3 and attribute.other_type_total:
            return QtGui.QBrush(QtGui.QColor(WARNING))

        return None

    # ------------------------------------------------------------ data access

    def set_attributes(self, attributes: Sequence[AggregatedAttribute]) -> None:
        """Replace every result."""
        self.beginResetModel()
        self._attributes = list(attributes)
        self.endResetModel()

    def attribute_at(self, row: int) -> Optional[AggregatedAttribute]:
        """Return the aggregated attribute for a row."""
        if 0 <= row < len(self._attributes):
            return self._attributes[row]
        return None

    def row_of(self, attribute: AggregatedAttribute) -> int:
        """Row of an aggregated attribute (-1 when it is not found)."""
        try:
            return self._attributes.index(attribute)
        except ValueError:
            return -1

    def attributes(self) -> List[AggregatedAttribute]:
        return list(self._attributes)

    def clear(self) -> None:
        self.set_attributes([])
