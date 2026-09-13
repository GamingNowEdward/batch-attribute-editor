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
from i18n import tr
from ui.qt import QSignalBlocker, Qt, QtWidgets, Signal
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
        super().__init__(tr("scope.title"), parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        #: (scope, radio button) pairs; the text is set by retranslate()
        self._scope_buttons: List[Tuple[TraversalScope, QtWidgets.QRadioButton]] = []
        for scope, _label in SCOPE_LABELS:
            button = QtWidgets.QRadioButton(tr(f"scope.option.{scope.value}"))
            button.setChecked(scope is TraversalScope.SELECTION_AND_DESCENDANTS)
            button.toggled.connect(
                lambda checked, value=scope: checked and self.scope_changed.emit(value)
            )
            layout.addWidget(button)
            self._scope_buttons.append((scope, button))

        row = QtWidgets.QHBoxLayout()
        self.refresh_button = QtWidgets.QPushButton(tr("scope.refresh_selection"))
        self.refresh_button.setObjectName("refreshBtn")
        self.refresh_button.setToolTip(tr("scope.refresh_tooltip"))
        self.refresh_button.clicked.connect(self.refresh_requested.emit)
        row.addWidget(self.refresh_button)
        row.addStretch(1)
        layout.addLayout(row)

        self.status_label = QtWidgets.QLabel(tr("scope.no_selection"))
        self.status_label.setObjectName("hintLabel")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

    def retranslate(self) -> None:
        """Refresh the section text after a language switch."""
        self.setTitle(tr("scope.title"))
        for scope, button in self._scope_buttons:
            button.setText(tr(f"scope.option.{scope.value}"))
        self.refresh_button.setText(tr("scope.refresh_selection"))
        self.refresh_button.setToolTip(tr("scope.refresh_tooltip"))

    def current_scope(self) -> TraversalScope:
        """The currently selected scope."""
        for scope, button in self._scope_buttons:
            if button.isChecked():
                return scope
        return TraversalScope.SELECTION_AND_DESCENDANTS

    def set_status(self, text: str) -> None:
        self.status_label.setText(text)


class SearchPanel(QtWidgets.QGroupBox):
    """Attribute search and filters."""

    search_requested = Signal(str, object, object)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(tr("search.title"), parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        top = QtWidgets.QHBoxLayout()
        self.pattern_edit = QtWidgets.QLineEdit()
        self.pattern_edit.setPlaceholderText(tr("search.placeholder"))
        self.pattern_edit.setClearButtonEnabled(True)
        self.pattern_edit.textChanged.connect(self._emit)
        self.pattern_edit.returnPressed.connect(self._emit)
        top.addWidget(self.pattern_edit, 1)

        self.mode_combo = QtWidgets.QComboBox()
        for index, (mode, _label) in enumerate(MATCH_MODE_LABELS):
            self.mode_combo.addItem(tr(f"search.mode.{mode.value}"), mode)
            self.mode_combo.setItemData(
                index, tr(f"search.mode.{mode.value}.tooltip"), Qt.ToolTipRole
            )
        self.mode_combo.currentIndexChanged.connect(self._emit)
        top.addWidget(self.mode_combo)
        layout.addLayout(top)

        filters = QtWidgets.QGridLayout()
        filters.setHorizontalSpacing(COLUMN_SPACING)
        filters.setVerticalSpacing(ROW_SPACING)

        #: (check box, translation key base) pairs; text is set by retranslate()
        self._checks: List[Tuple[QtWidgets.QCheckBox, str]] = []

        self.only_writable = self._checkbox("filter.writable_only")
        self.only_keyable = self._checkbox("filter.keyable_only")
        self.only_keyable.setChecked(True)
        self.only_user_defined = self._checkbox("filter.user_defined_only")
        self.hide_unsupported = self._checkbox("filter.hide_unsupported")
        self.hide_unsupported.setChecked(True)
        self.hide_compound_children = self._checkbox("filter.hide_compound_children")
        self.hide_locked = self._checkbox("filter.hide_locked")
        self.hide_connected = self._checkbox("filter.hide_connected")

        # Connect only once every check box exists: setChecked() above emits
        # toggled() immediately, and _emit() reads all of them.
        for box, _key_base in self._checks:
            box.toggled.connect(self._emit)

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

    def _checkbox(self, key_base: str) -> QtWidgets.QCheckBox:
        box = QtWidgets.QCheckBox(tr(key_base))
        box.setToolTip(tr(f"{key_base}.tooltip"))
        self._checks.append((box, key_base))
        return box

    def retranslate(self) -> None:
        """Refresh the section text after a language switch."""
        self.setTitle(tr("search.title"))
        self.pattern_edit.setPlaceholderText(tr("search.placeholder"))
        blocker = QSignalBlocker(self.mode_combo)
        for index, (mode, _label) in enumerate(MATCH_MODE_LABELS):
            self.mode_combo.setItemText(index, tr(f"search.mode.{mode.value}"))
            self.mode_combo.setItemData(
                index, tr(f"search.mode.{mode.value}.tooltip"), Qt.ToolTipRole
            )
        del blocker
        for box, key_base in self._checks:
            box.setText(tr(key_base))
            box.setToolTip(tr(f"{key_base}.tooltip"))

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

    #: Translation key of each field label (the field names stay the internal keys)
    FIELD_KEYS = {
        "Name": "details.field.name",
        "Type": "details.field.type",
        "Matched": "details.field.matched",
        "Writable": "details.field.writable",
        "Locked": "details.field.locked",
        "Connected": "details.field.connected",
        "Missing": "details.field.missing",
        "Type mismatch": "details.field.type_mismatch",
        "Other-type nodes": "details.field.other_type_nodes",
    }

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(tr("details.title"), parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(5)

        # Build both columns explicitly with one horizontal box per row instead of
        # using QFormLayout: the wrapped long-text field grows taller than a plain
        # label, and in a per-row box both widgets are stretched to the same row
        # height and vertically centred, so a label and its value always share one
        # baseline (QFormLayout placed the taller field lower than its label).
        self._labels: dict = {}
        self._values: dict = {}
        for field in self.FIELDS:
            label_widget = QtWidgets.QLabel(tr(self.FIELD_KEYS[field]))
            label_widget.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self._labels[field] = label_widget

            value = QtWidgets.QLabel("—")
            value.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            value.setTextInteractionFlags(
                value.textInteractionFlags() | Qt.TextSelectableByMouse
            )
            if field in self.LONG_FIELDS:
                value.setWordWrap(True)
                value.setMinimumHeight(30)
            self._values[field] = value

            row = QtWidgets.QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(12)
            row.addWidget(label_widget)
            row.addWidget(value, 1)

            layout.addLayout(row)

        self._update_label_widths()
        layout.addStretch(1)

    def _update_label_widths(self) -> None:
        """Keep one common label column even when the language changes the texts."""
        width = max(label.sizeHint().width() for label in self._labels.values())
        for label in self._labels.values():
            label.setFixedWidth(width)

    def retranslate(self) -> None:
        """Refresh the section text after a language switch."""
        self.setTitle(tr("details.title"))
        for field, label_widget in self._labels.items():
            label_widget.setText(tr(self.FIELD_KEYS[field]))
        self._update_label_widths()

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
        self._values["Other-type nodes"].setText(other_types or tr("common.none"))
        for field in ("Writable", "Locked", "Connected", "Missing", "Type mismatch"):
            self._values[field].setText(tr("details.validating"))

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
        super().__init__(tr("technical.title"), parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        self.text = QtWidgets.QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMinimumHeight(64)
        self.text.setMaximumHeight(120)
        self.text.setPlaceholderText(tr("technical.placeholder"))
        layout.addWidget(self.text)

    def retranslate(self) -> None:
        """Refresh the section text after a language switch."""
        self.setTitle(tr("technical.title"))
        self.text.setPlaceholderText(tr("technical.placeholder"))

    def clear(self) -> None:
        self.text.setPlainText("")

    def set_text(self, text: str) -> None:
        self.text.setPlainText(text or "")


class PreviewPanel(QtWidgets.QGroupBox):
    """Preview and apply."""

    preview_requested = Signal()
    apply_requested = Signal()

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(tr("preview.title"), parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        self.summary_label = QtWidgets.QLabel(tr("preview.set_value_hint"))
        self.summary_label.setObjectName("hintLabel")
        self.summary_label.setWordWrap(True)
        layout.addWidget(self.summary_label)

        self.node_list = QtWidgets.QPlainTextEdit()
        self.node_list.setReadOnly(True)
        self.node_list.setPlaceholderText(tr("preview.nodes_placeholder"))
        self.node_list.setMinimumHeight(72)
        layout.addWidget(self.node_list, 1)

        buttons = QtWidgets.QHBoxLayout()
        buttons.setSpacing(ROW_SPACING)
        self.preview_button = QtWidgets.QPushButton(tr("button.preview"))
        self.preview_button.setObjectName("previewButton")
        self.preview_button.setToolTip(tr("preview.preview_tooltip"))
        self.preview_button.clicked.connect(self.preview_requested.emit)
        buttons.addWidget(self.preview_button)

        self.apply_button = QtWidgets.QPushButton(tr("button.apply"))
        self.apply_button.setObjectName("applyButton")
        self.apply_button.setToolTip(tr("preview.apply_tooltip"))
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

    def retranslate(self) -> None:
        """Refresh the section text after a language switch.

        The summary / node list content is re-rendered by the main window, which
        owns the current report.
        """
        self.setTitle(tr("preview.title"))
        self.preview_button.setText(tr("button.preview"))
        self.preview_button.setToolTip(tr("preview.preview_tooltip"))
        self.apply_button.setText(tr("button.apply"))
        self.apply_button.setToolTip(tr("preview.apply_tooltip"))
        self.node_list.setPlaceholderText(tr("preview.nodes_placeholder"))

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
        super().__init__(tr("report.title"), parent)
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        # QTextEdit (not QPlainTextEdit): the audit trail is rendered as coloured
        # HTML, and only QTextEdit provides setHtml.
        self.text = QtWidgets.QTextEdit()
        self.text.setReadOnly(True)
        self.text.setPlaceholderText(tr("report.placeholder"))
        layout.addWidget(self.text)

        row = QtWidgets.QHBoxLayout()
        row.addStretch(1)
        self.clear_button = QtWidgets.QPushButton(tr("button.clear"))
        self.clear_button.setObjectName("clearBtn")
        self.clear_button.clicked.connect(self.clear)
        row.addWidget(self.clear_button)
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

    def retranslate(self) -> None:
        """Refresh the section text after a language switch.

        Audit entries keep the language they were written in (they are a record
        of past operations); the frame, the empty state and future entries use
        the newly selected language.
        """
        self.setTitle(tr("report.title"))
        self.clear_button.setText(tr("button.clear"))
        self.text.setPlaceholderText(tr("report.placeholder"))
        self.refresh()

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
                        f'<div style="color:{MUTED}">&nbsp;&nbsp;&nbsp;&nbsp;'
                        f'{html.escape(tr("report.detail_prefix"))} '
                        f'{html.escape(entry.detail)}</div>'
                    )
        if not blocks:
            blocks.append(
                f'<span style="color:{MUTED}">{html.escape(tr("report.no_operations"))}</span>'
            )
        self.text.setHtml("".join(blocks))
        scrollbar = self.text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
