"""Main window: assembles the Core session capabilities with the UI sections.

Design constraints:

* **The UI never manipulates Maya nodes directly** — all reading and writing goes through
  :class:`~core.session.BatchAttributeSession`.
* Uses ``MayaQWidgetDockableMixin`` + ``QWidget`` (**not** ``QMainWindow``): only a plain
  QWidget can be safely docked/tabbed by Maya.
* A **preview must be created first** before "Apply" can be clicked; any value change
  invalidates the preview and disables "Apply", so the user cannot write to the scene
  before seeing the full impact.
"""

from __future__ import annotations

import time
from typing import List, Optional, Tuple

from core.batch_setter import ValueCoercionError, ValuePayload, coerce_value
from core.results import ApplyReport, PreviewReport
from core.search import AggregatedAttribute, SearchResult
from core.selection import SelectionManager
from core.session import BatchAttributeSession
from core.traversal import TraversalScope
from i18n import get_language, normalize_language, set_language, tr
from ui.attribute_model import AttributeTableModel
from ui.editors.factory import ValueEditorFactory
from ui.panels import (
    DetailsPanel,
    LogPanel,
    PreviewPanel,
    ScopePanel,
    SearchPanel,
    TechnicalPanel,
)
from ui.qt import Qt, QtCore, QSignalBlocker, QtWidgets
from ui.settings import LanguageSettings
from ui.styles import (
    COLUMN_SPACING,
    GROUP_INSET,
    OUTER_MARGIN,
    ROW_SPACING,
    SECTION_SPACING,
    STYLESHEET,
)

try:  # pragma: no cover - needs the Maya GUI
    from maya.app.general.mayaMixin import MayaQWidgetDockableMixin

    _DOCKABLE_BASE = MayaQWidgetDockableMixin
except ImportError:  # pragma: no cover - allows importing this module outside Maya
    _DOCKABLE_BASE = object

WINDOW_OBJECT_NAME = "batchAttributeEditorWindow"
WORKSPACE_CONTROL_NAME = f"{WINDOW_OBJECT_NAME}WorkspaceControl"

#: Scene events that trigger cache invalidation (events that do not exist are skipped silently)
_SCENE_EVENTS = ("SceneOpened", "NewSceneOpened", "Undo", "Redo")

#: The Value editor area is sized to its content between these bounds, so a
#: Float3 / Color3 editor shows every channel while a huge array still scrolls.
VALUE_AREA_MIN_HEIGHT = 56
VALUE_AREA_MAX_HEIGHT = 420

#: Debounce for following the Maya selection (ms): high-frequency selection
#: changes are merged into a single refresh.
SELECTION_DEBOUNCE_MS = 350


class BatchAttributeEditorWindow(_DOCKABLE_BASE, QtWidgets.QWidget):  # type: ignore[misc]
    """Batch attribute editor main window."""

    #: Search debounce: while the user keeps typing, scan only once they pause
    SEARCH_DEBOUNCE_MS = 260

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName(WINDOW_OBJECT_NAME)
        self.setWindowTitle(tr("window.title"))
        self.setStyleSheet(STYLESHEET)
        self.resize(1280, 800)

        self.session = BatchAttributeSession()
        self.model = AttributeTableModel(self)
        self._language_settings = LanguageSettings()

        self._editor = None
        self._current: Optional[AggregatedAttribute] = None
        self._channels: Tuple = ()
        self._samples: dict = {}
        self._preview: Optional[PreviewReport] = None
        self._jobs: List[int] = []
        self._last_selection: List[str] = []
        self._last_result: Optional[SearchResult] = None
        self._last_summary = None
        self._validation_error: Optional[BaseException] = None

        #: Text currently shown above the editor:
        #: ``None`` = rebuild from the attribute, a key = re-render with ``tr``
        self._value_hint_key: Optional[str] = "value.select_hint"
        self._value_hint_params: dict = {}

        #: What the Preview panel currently shows (replayed on language switch):
        #: ``None`` | ("tr", key, params, level) | ("raw", text, level)
        #: | ("report", report, "preview"|"no_nodes"|"apply")
        self._preview_view = None

        self._search_timer = QtCore.QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(self.SEARCH_DEBOUNCE_MS)
        self._search_timer.timeout.connect(self.run_search)

        # Debounced refresh that follows the Maya selection; see _auto_refresh_selection
        self._selection_timer = QtCore.QTimer(self)
        self._selection_timer.setSingleShot(True)
        self._selection_timer.setInterval(SELECTION_DEBOUNCE_MS)
        self._selection_timer.timeout.connect(self._auto_refresh_selection)

        self._build_ui()
        self._install_scene_callbacks()
        self.refresh_selection()

    # ------------------------------------------------------------ construction

    def _build_ui(self) -> None:
        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN)
        root.setSpacing(ROW_SPACING)

        root.addLayout(self._build_language_bar())

        # Left column: the selection workflow (scope → search → results).
        # Right area: Details / Value / Preview column next to Technical / Log.
        self.main_splitter = QtWidgets.QSplitter(Qt.Horizontal)
        self.main_splitter.setChildrenCollapsible(False)
        self.main_splitter.addWidget(self._build_left_column())
        self.main_splitter.addWidget(self._build_inspector_area())
        self.main_splitter.setStretchFactor(0, 1)
        self.main_splitter.setStretchFactor(1, 1)
        root.addWidget(self.main_splitter, 1)

        self.scope_panel.scope_changed.connect(self._on_scope_changed)
        self.scope_panel.refresh_requested.connect(self.refresh_selection)
        self.search_panel.search_requested.connect(self._on_search_requested)
        self.preview_panel.preview_requested.connect(self.update_preview)
        self.preview_panel.apply_requested.connect(self.apply_changes)

    def _build_language_bar(self) -> QtWidgets.QHBoxLayout:
        """Top-right language selector (English / Chinese)."""
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(ROW_SPACING)
        row.addStretch(1)

        self.language_label = QtWidgets.QLabel(tr("language.label"))
        row.addWidget(self.language_label)

        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.addItem(tr("language.english"), "en")
        self.language_combo.addItem(tr("language.chinese"), "zh_CN")
        blocker = QSignalBlocker(self.language_combo)
        self.language_combo.setCurrentIndex(self._language_index())
        del blocker
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        row.addWidget(self.language_combo)
        return row

    def _language_index(self) -> int:
        """Combo index matching the active language (0 when it is not listed)."""
        target = normalize_language(get_language())
        for index in range(self.language_combo.count()):
            if self.language_combo.itemData(index) == target:
                return index
        return 0

    def _on_language_changed(self, index: int) -> None:
        """Switch the UI language immediately and persist the choice."""
        code = self.language_combo.itemData(index)
        if not code or not set_language(code):
            return
        self._language_settings.save(get_language())
        self._retranslate()

    def _build_left_column(self) -> QtWidgets.QWidget:
        """Workflow column: scope, search and results, stacked vertically."""
        column = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(column)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(SECTION_SPACING)

        self.scope_panel = ScopePanel()
        layout.addWidget(self.scope_panel)

        self.search_panel = SearchPanel()
        layout.addWidget(self.search_panel)

        layout.addWidget(self._build_results_view(), 1)

        column.setMinimumWidth(500)
        return column

    def _build_results_view(self) -> QtWidgets.QWidget:
        """Results table with a dedicated empty state page."""
        self.results_group = QtWidgets.QGroupBox(tr("results.title"))
        container = self.results_group
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        self._build_results_table()

        self.empty_state_label = QtWidgets.QLabel()
        self.empty_state_label.setObjectName("emptyStateLabel")
        self.empty_state_label.setAlignment(Qt.AlignCenter)
        self.empty_state_label.setWordWrap(True)

        self.results_stack = QtWidgets.QStackedWidget()
        self.results_stack.addWidget(self.table)
        self.results_stack.addWidget(self.empty_state_label)
        layout.addWidget(self.results_stack, 1)

        self.results_label = QtWidgets.QLabel(tr("results.nothing_searched"))
        self.results_label.setObjectName("hintLabel")
        layout.addWidget(self.results_label)
        return container

    def _build_results_table(self) -> None:
        """Build the result table with a stable column sizing policy."""
        self.table = QtWidgets.QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(False)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setMinimumHeight(120)

        header = self.table.horizontalHeader()
        header.setHighlightSections(False)
        header.setFixedHeight(26)
        header.setMinimumSectionSize(56)
        header.setStretchLastSection(True)
        header.setSectionResizeMode(0, QtWidgets.QHeaderView.Interactive)
        header.setSectionResizeMode(1, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(2, QtWidgets.QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QtWidgets.QHeaderView.Stretch)
        self.table.setColumnWidth(0, 240)

        self.table.selectionModel().selectionChanged.connect(self._on_selection_changed)

    def _build_inspector_area(self) -> QtWidgets.QWidget:
        """Right area: Details/Value column next to the Technical/Log column.

        The split is roughly 65 : 35 so the info column stays wider than the
        inspector while both share the same vertical space.
        """
        container = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(COLUMN_SPACING)

        mid = QtWidgets.QWidget()
        mid_layout = QtWidgets.QVBoxLayout(mid)
        mid_layout.setContentsMargins(0, 0, 0, 0)
        mid_layout.setSpacing(ROW_SPACING)

        self.details_panel = DetailsPanel()
        mid_layout.addWidget(self.details_panel)

        self.value_group = self._build_value_group()
        mid_layout.addWidget(self.value_group)

        # Preview sits directly under Value; it absorbs the remaining height so the
        # change list can use it.
        self.preview_panel = PreviewPanel()
        mid_layout.addWidget(self.preview_panel, 1)
        mid.setMinimumWidth(300)

        side = QtWidgets.QWidget()
        side_layout = QtWidgets.QVBoxLayout(side)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(ROW_SPACING)

        self.technical_panel = TechnicalPanel()
        side_layout.addWidget(self.technical_panel)

        self.log_panel = LogPanel()
        side_layout.addWidget(self.log_panel, 1)
        side.setMinimumWidth(220)

        layout.addWidget(mid, 65)
        layout.addWidget(side, 35)
        return container

    def _build_value_group(self) -> QtWidgets.QGroupBox:
        """Value editor group; the editor area scrolls when an attribute has many channels."""
        group = QtWidgets.QGroupBox(tr("value.title"))
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        self.value_hint = QtWidgets.QLabel(tr("value.select_hint"))
        self.value_hint.setObjectName("hintLabel")
        self.value_hint.setWordWrap(True)
        layout.addWidget(self.value_hint)

        self.value_container = QtWidgets.QWidget()
        self.value_container_layout = QtWidgets.QVBoxLayout(self.value_container)
        self.value_container_layout.setContentsMargins(0, 0, 0, 0)
        self.value_container_layout.setSpacing(ROW_SPACING)

        self.value_scroll = QtWidgets.QScrollArea()
        self.value_scroll.setWidgetResizable(True)
        self.value_scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.value_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.value_scroll.setWidget(self.value_container)
        layout.addWidget(self.value_scroll)

        self._sync_value_area_height()
        return group

    def _value_content_height(self) -> int:
        """Height needed by the editor widgets plus layout margins / spacing.

        ``QLayout.sizeHint()`` ignores child widgets that have not been shown yet
        (measured: it returns 0 right after an editor is created), so the widget
        size hints are summed directly - that value is correct immediately.
        """
        layout = self.value_container_layout
        margins = layout.contentsMargins()
        height = margins.top() + margins.bottom()
        count = layout.count()
        for index in range(count):
            widget = layout.itemAt(index).widget()
            if widget is not None:
                height += widget.sizeHint().height()
        if count > 1:
            height += (count - 1) * layout.spacing()
        return height

    def _sync_value_area_height(self) -> None:
        """Size the Value scroll area to its content, bounded.

        Explicit sizing keeps a Float3 / Color3 editor fully visible, a small
        scalar compact, and caps a huge array so it scrolls instead of eating the
        whole column.
        """
        if not hasattr(self, "value_scroll"):
            return
        content = self._value_content_height()
        height = max(VALUE_AREA_MIN_HEIGHT, min(content, VALUE_AREA_MAX_HEIGHT))
        self.value_scroll.setFixedHeight(height)

    # ------------------------------------------------------------ scene callbacks

    def _install_scene_callbacks(self) -> None:
        """Register scene/selection events so the tool follows Maya automatically.

        The callbacks stay extremely cheap: the scene events only invalidate the
        cache, the selection event only (re)starts the debounce timer — all the
        actual scanning happens once, after the user pauses.
        """
        from maya import cmds

        for event in _SCENE_EVENTS:
            try:
                job = cmds.scriptJob(event=[event, self._on_scene_event], protected=True)
            except (RuntimeError, TypeError):
                continue
            self._jobs.append(job)

        try:
            job = cmds.scriptJob(
                event=["SelectionChanged", self._on_selection_event], protected=True
            )
        except (RuntimeError, TypeError):
            job = None
        if job is not None:
            self._jobs.append(job)

    def _on_scene_event(self) -> None:
        """Scene changed: drop the cache and follow the (possibly new) selection."""
        self.session.invalidate_cache()
        self._selection_timer.start()

    def _on_selection_event(self) -> None:
        """Maya selection changed: schedule one debounced refresh (no scanning here)."""
        self._selection_timer.start()

    def _auto_refresh_selection(self) -> None:
        """Follow the Maya selection with a debounced, cache-friendly refresh.

        Performance: the debounce merges rapid selection changes, an unchanged
        object set is skipped entirely, pure component selections are ignored, and
        the scan cache is kept (selection changes do not affect attribute tables),
        which makes the refresh nearly instant even on large scenes.
        """
        raw = SelectionManager.current_selection()
        objects = [name for name in raw if "." not in name]
        if raw and not objects:
            # Pure component selection (faces / edges / points / UVs): the tool
            # works on whole nodes, so keep the current result.
            return
        if objects == self._last_selection:
            return
        self._run_busy(lambda: self._refresh_selection_impl(clear_cache=False))

    def teardown(self) -> None:
        """Clean up the scriptJobs (called when the window is closed or reopened)."""
        from maya import cmds

        self._selection_timer.stop()
        for job in self._jobs:
            try:
                if cmds.scriptJob(exists=job):
                    cmds.scriptJob(kill=job, force=True)
            except (RuntimeError, TypeError):
                continue
        self._jobs = []

    # ------------------------------------------------------------ selection and search

    def refresh_selection(self) -> None:
        """Force a full refresh: clear the scan cache and re-read the selection.

        The tool also follows the Maya selection automatically; this button stays
        for a forced rescan (e.g. attributes changed by script, where the cache
        cannot notice the change).
        """
        self._run_busy(lambda: self._refresh_selection_impl(clear_cache=True))

    def _refresh_selection_impl(self, clear_cache: bool = True) -> None:
        scope = self.scope_panel.current_scope()
        try:
            if clear_cache:
                self.session.refresh()
            else:
                # Selection-only change: keep the scan cache, it is still valid and
                # keeps following the selection fast on large scenes.
                self.session.resolve_selection(scope)
        except Exception as exc:  # noqa: BLE001 - the UI must not crash on a single failure
            self.scope_panel.set_status(tr("status.selection_failed", error=exc))
            return

        self._last_selection = [
            name for name in SelectionManager.current_selection() if "." not in name
        ]
        self.scope_panel.set_status(self.session.state.describe())
        self._current = None
        self._editor = None
        self._last_summary = None
        self._validation_error = None
        self._clear_value_area()
        self.details_panel.clear()
        self.technical_panel.clear()
        self._show_preview_message("preview.set_value_hint")
        self.run_search()

    def _on_scope_changed(self, scope: TraversalScope) -> None:
        self.session.collect_nodes(scope)
        self.scope_panel.set_status(self.session.state.describe())
        self.run_search()

    def _on_search_requested(self, _pattern: str, _mode, _filters) -> None:
        # Debounce: while typing, only scan after a pause, so a large scene is not fully
        # rescanned on every keystroke
        self._search_timer.start()

    def run_search(self) -> None:
        """Run the search and refresh the results table."""
        self._search_timer.stop()

        def action() -> None:
            result: SearchResult = self.session.search(
                self.search_panel.pattern(),
                self.search_panel.filters(),
                self.search_panel.mode(),
            )
            self._apply_search_result(result)

        self._run_busy(action)

    def _apply_search_result(self, result: SearchResult) -> None:
        self._last_result = result
        self.model.set_attributes(result.attributes)

        if result.attributes:
            self.results_stack.setCurrentWidget(self.table)
        else:
            self.results_stack.setCurrentWidget(self.empty_state_label)

        self._update_result_labels(result)

        self._current = None
        self._editor = None
        self._last_summary = None
        self._validation_error = None
        self._clear_value_area()
        self.details_panel.clear()
        self.technical_panel.clear()

        if result.attributes:
            self.table.selectRow(0)

    def _update_result_labels(self, result: SearchResult) -> None:
        """Refresh the result summary / empty state (replayed on language switch)."""
        if result.scanned_nodes == 0:
            # The most common case: the window just opened and nothing is selected in the viewport
            self.empty_state_label.setText(tr("results.empty_no_nodes"))
            self.results_label.setText("")
        elif result.is_empty:
            self.empty_state_label.setText(
                tr("results.empty_no_match", count=result.scanned_nodes)
            )
            self.results_label.setText("")
        else:
            self.results_label.setText(result.describe())

    # ------------------------------------------------------------ the selected attribute

    def _on_selection_changed(self, *_args) -> None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return
        attribute = self.model.attribute_at(indexes[0].row())
        if attribute is None:
            return
        self._current = attribute
        self._last_summary = None
        self._validation_error = None
        self._show_preview_message("preview.set_value_hint")
        self.details_panel.set_basic(attribute)
        self.technical_panel.set_text(attribute.definition.describe())
        self._build_editor(attribute)
        # Validation can be slow, so run it one beat later and let the interface refresh first
        QtCore.QTimer.singleShot(0, lambda: self._run_busy(
            lambda: self._validate_current(attribute)))

    def _validate_current(self, attribute: AggregatedAttribute) -> None:
        """Fully validate the current attribute (Locked / Connected / Missing statistics)."""
        if attribute is not self._current:
            return
        try:
            summary = attribute.summary(force=True)
        except Exception as exc:  # noqa: BLE001
            self._validation_error = exc
            self._show_validation_error()
            return
        if attribute is self._current:
            self._last_summary = summary
            self.details_panel.set_summary(summary)

    def _show_validation_error(self) -> None:
        """Render the stored validation failure (replayed on language switch)."""
        if self._validation_error is None:
            return
        text = tr("status.validation_failed", error=self._validation_error)
        self.details_panel.set_note(text)
        self.technical_panel.set_text(text)

    def _clear_value_area(self) -> None:
        while self.value_container_layout.count():
            item = self.value_container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self._set_value_hint("value.select_hint")
        self._sync_value_area_height()

    def _set_value_hint(self, key: Optional[str], **params) -> None:
        """Show a static (translatable) hint above the editor."""
        self._value_hint_key = key
        self._value_hint_params = params
        if key is not None:
            self.value_hint.setText(tr(key, **params))

    def _set_dynamic_value_hint(self) -> None:
        """Show the hint built from the current attribute (type, units, ...)."""
        self._value_hint_key = None
        self._value_hint_params = {}
        if self._current is not None:
            self.value_hint.setText(
                self._value_hint_text(self._current, self._channels, self._samples)
            )

    def _build_editor(self, attribute: AggregatedAttribute) -> None:
        """Create the value editor for the attribute type."""
        self._clear_value_area()

        if not attribute.definition.supports_editing:
            self._set_value_hint("value.not_editable", type=attribute.type_label)
            return

        channels = self.session.channels_for(attribute)
        self._channels = channels
        if not channels:
            self._set_value_hint("value.no_channels")
            return

        samples = self.session.sample_values(attribute, channels)
        self._samples = samples
        editor = ValueEditorFactory.create(
            attribute.definition, channels, samples, self.value_container
        )
        if editor is None:
            self._set_value_hint("value.editor_failed")
            return

        self._editor = editor
        editor.changed.connect(self._on_value_changed)
        self.value_container_layout.addWidget(editor)
        editor.show()

        reload_callback = getattr(editor, "set_reload_callback", None)
        if callable(reload_callback):
            reload_callback(lambda: self._reload_values(attribute, editor))

        self._set_dynamic_value_hint()
        self._sync_value_area_height()

    def _value_hint_text(self, attribute: AggregatedAttribute, channels, samples) -> str:
        """Hint above the editor: type, channel count, units and the "other types excluded" note."""
        parts = [tr("value.hint.type_nodes",
                    type=attribute.type_label, count=attribute.node_count)]
        if len(channels) > 1:
            parts.append(tr("value.hint.channels", count=len(channels)))
        units = [widget for widget in {getattr(c, "unit_type", None) for c in channels} if widget]
        if units:
            parts.append(tr("value.hint.units"))
        if not samples:
            parts.append(tr("value.hint.no_samples"))
        if attribute.other_type_total:
            parts.append(tr("value.hint.other_types",
                            count=attribute.other_type_total))
        return " · ".join(parts)

    def _reload_values(self, attribute: AggregatedAttribute, editor) -> None:
        """Read the current scene values into the editor again."""
        samples = self.session.sample_values(attribute, self._channels)
        if not samples:
            self._set_value_hint("value.read_failed")
            return
        self._samples = samples
        editor.set_values(samples)
        self._on_value_changed()

    def _on_value_changed(self) -> None:
        """A value changed → the preview is invalid → disable "Apply"."""
        self._preview = None
        self._show_preview_message("preview.values_changed", level="warning")

    # ------------------------------------------------------------ preview and apply

    def _build_payload(self) -> Tuple[Optional[ValuePayload], List[str]]:
        """Turn the input from the editor into a type-safe payload."""
        if self._editor is None or self._current is None:
            return None, [tr("preview.select_attribute")]

        # A typed but not-yet-committed numeric edit must be committed before
        # reading, otherwise the write would silently use the previous value.
        commit = getattr(self._editor, "commit", None)
        if callable(commit):
            commit()

        values = self._editor.values()
        if not values:
            return None, [tr("preview.no_channels_enabled")]

        channels = {channel.key: channel for channel in self._channels}
        payload = ValuePayload()
        problems: List[str] = []
        for key, value in values.items():
            channel = channels.get(key)
            if channel is None:
                continue
            try:
                payload.set_raw(channel, coerce_value(value, channel.kind))
            except ValueCoercionError as exc:
                problems.append(f"{channel.display_label}: {exc}")
        if problems:
            return None, problems
        return payload, []

    def update_preview(self) -> None:
        """Create the preview."""
        payload, problems = self._build_payload()
        if problems:
            self._show_preview_raw("; ".join(problems), level="error")
            return
        if payload is None:
            self._show_preview_message("preview.nothing_to_write", level="warning")
            return

        attribute = self._current
        assert attribute is not None

        def action() -> None:
            report = self.session.preview(attribute, payload)
            self._preview = report
            if report.will_modify == 0:
                self._show_preview_report(report, kind="no_nodes")
                return
            self._show_preview_report(report, kind="preview")

        self._run_busy(action)

    def apply_changes(self) -> None:
        """Run the batch modification (the whole batch is a single Undo)."""
        if self._preview is None:
            self._show_preview_message("preview.require_preview", level="warning")
            return

        payload, problems = self._build_payload()
        if problems or payload is None:
            self._show_preview_raw(
                "; ".join(problems) or tr("preview.nothing_to_write"), level="error"
            )
            return

        attribute = self._current
        assert attribute is not None

        def action() -> None:
            report: ApplyReport = self.session.apply(attribute, payload)
            self._preview = None
            self._show_preview_report(report, kind="apply")
            self.log_panel.append_log(report.log, self._audit_header(report))
            # Writing may change the lock state; revalidate so the details stay accurate
            QtCore.QTimer.singleShot(0, lambda: self._run_busy(
                lambda: self._validate_current(attribute)))

        self._run_busy(action)

    # ------------------------------------------------------------ preview panel state

    def _show_preview_message(self, key: str, level: str = "hint", **params) -> None:
        """Show a translatable hint; remembered so a language switch can replay it."""
        self._preview_view = ("tr", key, params, level)
        self.preview_panel.set_message(tr(key, **params), level=level)

    def _show_preview_raw(self, text: str, level: str = "error") -> None:
        """Show text that already contains data (input errors); not re-translated."""
        self._preview_view = ("raw", text, level)
        self.preview_panel.set_message(text, level=level)

    def _show_preview_report(self, report, kind: str = "preview") -> None:
        """Show a Preview/Apply report; rendered again on every language switch."""
        self._preview_view = ("report", report, kind)
        self._replay_preview_view()

    def _replay_preview_view(self) -> None:
        """Render the stored Preview panel state in the active language."""
        view = self._preview_view
        if view is None:
            self.preview_panel.set_message(tr("preview.set_value_hint"))
            return

        kind = view[0]
        if kind == "tr":
            _kind, key, params, level = view
            self.preview_panel.set_message(tr(key, **params), level=level)
        elif kind == "raw":
            _kind, text, level = view
            self.preview_panel.set_message(text, level=level)
        elif kind == "report":
            _kind, report, mode = view
            if mode == "preview":
                self.preview_panel.set_preview(report.describe(), report.detail_text())
            elif mode == "no_nodes":
                self.preview_panel.set_message(
                    tr("preview.no_nodes_modified",
                       detail=report.skip_summary() or tr("preview.check_filters")),
                    level="warning",
                )
                self.preview_panel.node_list.setPlainText(report.detail_text())
            else:  # "apply"
                self.preview_panel.set_report(report.describe())
                self.preview_panel.undo_hint.setText(tr("preview.undo_hint"))

    # ------------------------------------------------------------ audit header

    @staticmethod
    def _audit_header(report: ApplyReport) -> str:
        """Header line of one audit batch: attribute, value, time and counts."""
        counts = [tr("log.count_changed", count=report.succeeded)]
        if report.skipped_count:
            counts.append(tr("log.count_skipped", count=report.skipped_count))
        if report.failed:
            counts.append(tr("log.count_failed", count=report.failed))
        return tr("log.audit_header",
                  attribute=report.attribute_name,
                  value=report.value_repr,
                  time=time.strftime("%H:%M:%S"),
                  counts=", ".join(counts))

    # ------------------------------------------------------------ retranslation

    def _retranslate(self) -> None:
        """Apply the newly selected language everywhere (no widget is recreated)."""
        self.setWindowTitle(tr("window.title"))
        self.language_label.setText(tr("language.label"))

        blocker = QSignalBlocker(self.language_combo)
        self.language_combo.setItemText(0, tr("language.english"))
        self.language_combo.setItemText(1, tr("language.chinese"))
        del blocker

        self.scope_panel.retranslate()
        self.search_panel.retranslate()
        self.model.retranslate()
        self.results_group.setTitle(tr("results.title"))
        self.value_group.setTitle(tr("value.title"))
        self.details_panel.retranslate()
        self.technical_panel.retranslate()
        self.preview_panel.retranslate()
        self.log_panel.retranslate()

        self.scope_panel.set_status(self.session.state.describe())
        if self._last_result is not None:
            self._update_result_labels(self._last_result)

        if self._current is None:
            self._set_value_hint("value.select_hint")
        elif self._value_hint_key is None:
            self._set_dynamic_value_hint()
        else:
            self.value_hint.setText(
                tr(self._value_hint_key, **self._value_hint_params)
            )

        if self._current is not None:
            self.details_panel.set_basic(self._current)
            self.technical_panel.set_text(self._current.definition.describe())
        if self._last_summary is not None and self._current is not None:
            self.details_panel.set_summary(self._last_summary)
        if self._validation_error is not None:
            self._show_validation_error()

        retranslate_editor = getattr(self._editor, "retranslate", None)
        if callable(retranslate_editor):
            retranslate_editor()

        self._replay_preview_view()

    # ------------------------------------------------------------ busy wrapper

    def _run_busy(self, action) -> None:
        """Run an operation that may be slow, showing a wait cursor meanwhile.

        Core is synchronous; this only guarantees the user gets "working" feedback,
        and that **no exception ever crashes a panel** — errors are shown in the status
        area and the log section.
        """
        QtWidgets.QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            QtWidgets.QApplication.processEvents()
            action()
        except Exception as exc:  # noqa: BLE001 - the UI must be fault tolerant
            import traceback

            self.scope_panel.set_status(tr("status.operation_failed", error=exc))
            self.log_panel.append(f"[ERROR] {exc}\n{traceback.format_exc()}")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
