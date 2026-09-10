"""Interface sections: Scope / Search / Details / Preview / Log.

Each section is a standalone widget that only displays information and emits signals; it
**never touches Maya directly**. The real orchestration lives in :mod:`ui.main_window`.
"""

from __future__ import annotations

import html
from typing import List, Optional, Tuple

from core.compatibility import ValidationStatus, status_label
from core.search import (
    MATCH_MODE_LABELS,
    AggregatedAttribute,
    MatchMode,
    SearchFilters,
)
from core.traversal import SCOPE_LABELS, TraversalScope
from ui.qt import Qt, QtWidgets, Signal
from ui.styles import (
    ACCENT,
    COLUMN_SPACING,
    ERROR,
    GROUP_INSET,
    MUTED,
    ROW_SPACING,
    TEXT,
    WARNING,
)
from utils.logging_utils import LogEntry, LogLevel


class ScopePanel(QtWidgets.QGroupBox):
    """Node search scope."""

    scope_changed = Signal(object)
    refresh_requested = Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__("Scope · Search Range", parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        self._buttons: List[QtWidgets.QRadioButton] = []
        for scope, label in SCOPE_LABELS:
            button = QtWidgets.QRadioButton(label)
            button.setChecked(scope is TraversalScope.SELECTION_AND_DESCENDANTS)
            button.toggled.connect(
                lambda checked, value=scope: checked and self.scope_changed.emit(value)
            )
            layout.addWidget(button)
            self._buttons.append(button)

        row = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton("Refresh Selection")
        self.refresh_button.setObjectName("refreshBtn")
        self.refresh_button.setToolTip("Read the current selection again and clear the scan cache")
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        row.addWidget(self.refresh_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.status_label = QtWidgets.QLabel("No nodes selected")
        self.status_label.setObjectName("hintLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def current_scope(self) -> TraversalScope:
        """The currently selected scope."""
        for scope, _label in SCOPE_LABELS:
            index = [item[0] for item in SCOPE_LABELS].index(scope)
            if self._buttons[index].isChecked():
                return scope
        return TraversalScope.SELECTION_AND_DESCENDANTS

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)


class SearchPanel(QtWidgets.QGroupBox):
    """Attribute search and filters."""

    search_requested = Signal(str, object, object)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__("Attribute Search", parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        top = QtWidgets.QHBoxLayout()
        self.pattern_edit = QtWidgets.QLineEdit()
        self.pattern_edit.setPlaceholderText("Attribute name, e.g. visibility / color / custom")
        self.pattern_edit.setClearButtonEnabled(True)
        self.pattern_edit.textChanged.connect(self._emit)
        self.pattern_edit.returnPressed.connect(self._emit)
        top.addWidget(self.pattern_edit, 1)

        self.mode_combo = QtWidgets.QComboBox()
        for mode, label in MATCH_MODE_LABELS:
            self.mode_combo.addItem(label, mode)
        self.mode_combo.currentIndexChanged.connect(self._emit)
        top.addWidget(self.mode_combo)
        layout.addLayout(top)

        filters = QtWidgets.QGridLayout()
        filters.setHorizontalSpacing(COLUMN_SPACING)
        filters.setVerticalSpacing(ROW_SPACING)

        self.only_writable = self._checkbox("Writable only",
                                            "Hide attributes Maya reports as read-only")
        self.only_keyable = self._checkbox("Keyable only",
                                           "Keep only attributes that can be keyframed")
        self.only_user_defined = self._checkbox("User defined only",
                                                "Keep only User Defined attributes")
        self.hide_unsupported = self._checkbox("Hide unsupported",
                                               "Hide matrix / message and other non-editable types")
        self.hide_unsupported.setChecked(True)
        self.hide_compound_children = self._checkbox(
            "Hide compound children",
            "Hide children such as translateX and keep only the parent attribute"
        )
        self.hide_locked = self._checkbox("Hide locked",
                                          "Requires per-node validation — slower on large scenes")
        self.hide_connected = self._checkbox(
            "Hide connected",
            "Requires per-node validation — slower on large scenes"
        )

        # Two rows of four / three so the column stays usable at ~500 px width.
        filters.addWidget(self.only_writable, 0, 0)
        filters.addWidget(self.only_keyable, 0, 1)
        filters.addWidget(self.only_user_defined, 0, 2)
        filters.addWidget(self.hide_unsupported, 0, 3)
        filters.addWidget(self.hide_compound_children, 1, 0)
        filters.addWidget(self.hide_locked, 1, 1)
        filters.addWidget(self.hide_connected, 1, 2)
        filters.setColumnStretch(3, 1)
        layout.addLayout(filters)

    def _checkbox(self, text: str, tooltip: str) -> QtWidgets.QCheckBox:
        box = QtWidgets.QCheckBox(text)
        box.setToolTip(tooltip)
        box.toggled.connect(self._emit)
        return box

    def _emit(self, *_args) -> None:
        self.search_requested.emit(self.pattern(), self.mode(), self.filters())

    def pattern(self) -> str:
        return self.pattern_edit.text()

    def mode(self) -> MatchMode:
        value = self.mode_combo.currentData()
        return value if isinstance(value, MatchMode) else MatchMode.CONTAINS

    def filters(self) -> SearchFilters:
        return SearchFilters(
            only_writable=self.only_writable.isChecked(),
            only_keyable=self.only_keyable.isChecked(),
            only_user_defined=self.only_user_defined.isChecked(),
            hide_unsupported=self.hide_unsupported.isChecked(),
            hide_compound_children=self.hide_compound_children.isChecked(),
            hide_locked=self.hide_locked.isChecked(),
            hide_connected=self.hide_connected.isChecked(),
        )


class DetailsPanel(QtWidgets.QGroupBox):
    """Detail statistics for the selected attribute.

    The fields form one strict label column (right aligned) and one value column
    (left aligned), so a long label such as "Other-type nodes" never shifts the
    values around. No padding is faked with spaces.
    """

    FIELDS = ("Name", "Type", "Matched", "Writable", "Locked", "Connected",
              "Missing", "Type mismatch", "Other-type nodes")
    LONG_FIELDS = ("Other-type nodes",)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__("Attribute Details", parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(5)

        # Build both columns explicitly with one horizontal box per row instead of
        # using QFormLayout: the wrapped long-text field grows taller than a plain
        # label, and in a per-row box both widgets are stretched to the same row
        # height and vertically centred, so a label and its value always share one
        # baseline (QFormLayout placed the taller field lower than its label).
        labels: List[QtWidgets.QLabel] = []
        values: List[QtWidgets.QLabel] = []
        for field in self.FIELDS:
            label_widget = QtWidgets.QLabel(f"{field}:")
            label_widget.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

            value = QtWidgets.QLabel("—")
            value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            value.setTextInteractionFlags(value.textInteractionFlags() | 0x1)
            if field in self.LONG_FIELDS:
                value.setWordWrap(True)
                value.setMinimumHeight(30)

            labels.append(label_widget)
            values.append(value)

        label_width = max(label_widget.sizeHint().width() for label_widget in labels)

        self._values = {}
        for field, label_widget, value in zip(self.FIELDS, labels, values):
            label_widget.setFixedWidth(label_width)

            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(12)
            row.addWidget(label_widget)
            row.addWidget(value, 1)

            layout.addLayout(row)
            self._values[field] = value

        layout.addStretch(1)

    def clear(self) -> None:
        for label in self._values.values():
            label.setText("—")

    def set_basic(self, attribute: AggregatedAttribute) -> None:
        """Show the cheap information first; validation results follow later."""
        self._values["Name"].setText(attribute.display_name)
        self._values["Type"].setText(attribute.type_label)
        self._values["Matched"].setText(str(attribute.node_count))
        other_types = ", ".join(
            f"{label} × {count}" for label, count in attribute.other_types.items()
        )
        self._values["Other-type nodes"].setText(other_types or "none")
        for field in ("Writable", "Locked", "Connected", "Missing", "Type mismatch"):
            self._values[field].setText("Validating…")

    def set_summary(self, summary) -> None:
        """Fill in the validation statistics."""
        self._values["Writable"].setText(f"{summary.writable} / {summary.total}")
        self._values["Locked"].setText(str(summary.count(ValidationStatus.LOCKED)))
        self._values["Connected"].setText(str(summary.count(ValidationStatus.CONNECTED)))
        self._values["Missing"].setText(str(summary.count(ValidationStatus.MISSING)))
        self._values["Type mismatch"].setText(str(summary.count(ValidationStatus.TYPE_MISMATCH)))

    def set_note(self, text: str) -> None:
        """Reset the numbers when validation cannot be performed."""
        for field in ("Writable", "Locked", "Connected", "Missing", "Type mismatch"):
            self._values[field].setText("—")


class TechnicalPanel(QtWidgets.QGroupBox):
    """Technical metadata of the selected attribute (read-only).

    Holds the definition description that used to live inside the Details panel,
    giving the right column a dedicated inspector area.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__("Technical Details", parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        self.text = QtWidgets.QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(64)
        self.text.setMaximumHeight(120)
        self.text.setPlaceholderText("Technical details (select an attribute)")
        layout.addWidget(self.text)

    def clear(self) -> None:
        self.text.setPlainText("")

    def set_text(self, text: str) -> None:
        self.text.setPlainText(text or "")


class PreviewPanel(QtWidgets.QGroupBox):
    """Preview and apply."""

    preview_requested = Signal()
    apply_requested = Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__("Preview · Apply", parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        self.summary_label = QtWidgets.QLabel('Set a value, then click "Preview"')
        self.summary_label.setObjectName("hintLabel")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.node_list = QtWidgets.QPlainTextEdit()
        self.node_list.setReadOnly(True)
        self.node_list.setPlaceholderText("Nodes that will be modified will be listed here")
        self.node_list.setMinimumHeight(72)
        layout.addWidget(self.node_list, 1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(ROW_SPACING)
        self.preview_button = QtWidgets.QPushButton("Preview")
        self.preview_button.setObjectName("previewButton")
        self.preview_button.setToolTip(
            "Check which nodes will change and which will be skipped (does not write to the scene)"
        )
        self.preview_button.clicked.connect(self.preview_requested.emit)
        buttons.addWidget(self.preview_button)

        self.apply_button = QtWidgets.QPushButton("Apply")
        self.apply_button.setObjectName("applyButton")
        self.apply_button.setToolTip(
            "A preview is required before applying; the whole batch is a single Undo"
        )
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply_requested.emit)
        buttons.addWidget(self.apply_button)

        buttons.addStretch(1)
        layout.addLayout(buttons)

        # The undo hint lives on its own wrapped line: in the narrow middle column
        # it would otherwise squeeze the buttons.
        self.undo_hint = QtWidgets.QLabel("")
        self.undo_hint.setObjectName("hintLabel")
        self.undo_hint.setWordWrap(True)
        layout.addWidget(self.undo_hint)

    def set_preview(self, text: str, details: str) -> None:
        """Show the preview result and enable "Apply".

        ``details`` is the full per-channel change list plus the skip list built by
        ``PreviewReport.detail_text()``.
        """
        self.summary_label.setText(text)
        self.summary_label.setObjectName("successLabel")
        self._restyle(self.summary_label)
        self.node_list.setPlainText(details)
        self.apply_button.setEnabled(True)

    def set_message(self, text: str, level: str = "hint") -> None:
        """Show a hint and disable "Apply" (the preview is no longer valid)."""
        self.summary_label.setText(text)
        self.summary_label.setObjectName(f"{level}Label" if level != "hint" else "hintLabel")
        self._restyle(self.summary_label)
        self.apply_button.setEnabled(False)

    def set_report(self, text: str) -> None:
        """Show the apply result."""
        self.summary_label.setText(text)
        self.summary_label.setObjectName("successLabel")
        self._restyle(self.summary_label)
        self.apply_button.setEnabled(False)

    @staticmethod
    def _restyle(widget: QtWidgets.QWidget) -> None:
        """The stylesheet has to be reapplied after objectName changes."""
        style = widget.style()
        if style is not None:
            style.unpolish(widget)
            style.polish(widget)


_LOG_LEVEL_COLORS = {
    LogLevel.INFO: TEXT,
    LogLevel.WARNING: WARNING,
    LogLevel.ERROR: ERROR,
}


class LogPanel(QtWidgets.QGroupBox):
    """Operation audit trail.

    Every Apply appends one batch: a header line (attribute, value, time, counts)
    followed by one entry per written channel (``old → new``), skipped node or
    failure. Recent batches are retained so the user can review what was changed
    after the fact — something the preview (an up-front snapshot) cannot do.
    """

    MAX_BATCHES = 20

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__("Report · Log", parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        # QTextEdit (not QPlainTextEdit): the audit trail is rendered as coloured
        # HTML, and only QTextEdit provides setHtml.
        self.text = QtWidgets.QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText("Applied changes will be audited here")
        layout.addWidget(self.text)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        clear = QtWidgets.QPushButton("Clear")
        clear.setObjectName("clearBtn")
        clear.clicked.connect(self.clear)
        row.addWidget(clear)
        layout.addLayout(row)

        # [(header, entries), ...]; the oldest batches are dropped beyond MAX_BATCHES
        self._batches: List[Tuple[str, List[LogEntry]]] = []

    # ------------------------------------------------------------ history

    def append_log(self, log, header: str) -> None:
        """Append one operation's audit trail, keeping the earlier history."""
        self._batches.append((header, list(log.entries)))
        self._trim()
        self.refresh()

    def append(self, message: str) -> None:
        """Append a raw error line (UI-level fallback); rendered as an ERROR entry."""
        self._batches.append(("", [LogEntry(level=LogLevel.ERROR, message=message)]))
        self._trim()
        self.refresh()

    def clear(self) -> None:
        """Drop the whole audit history."""
        self._batches = []
        self.refresh()

    def _trim(self) -> None:
        while len(self._batches) > self.MAX_BATCHES:
            self._batches.pop(0)

    # ------------------------------------------------------------ rendering

    def refresh(self) -> None:
        """Redraw every retained batch (colours by level; failure details always shown)."""
        blocks: List[str] = []
        for header, entries in self._batches:
            if header:
                blocks.append(f'<div style="color:{ACCENT}">{html.escape(header)}</div>')
            for entry in entries:
                color = _LOG_LEVEL_COLORS.get(entry.level, TEXT)
                # A raw message may contain newlines (e.g. a traceback): render it
                # line by line, otherwise HTML would collapse the breaks.
                for line in entry.format_line().splitlines() or [""]:
                    blocks.append(f'<div style="color:{color}">{html.escape(line)}</div>')
                if entry.detail:
                    blocks.append(
                        f'<div style="color:{MUTED}">&nbsp;&nbsp;&nbsp;&nbsp;detail: '
                        f'{html.escape(entry.detail)}</div>'
                    )
        if not blocks:
            blocks.append(f'<span style="color:{MUTED}">(no operations yet)</span>')
        self.text.setHtml("".join(blocks))
        scrollbar = self.text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
