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
from ui.qt import Qt, QtCore, QtWidgets
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
        self.setWindowTitle("Batch Attribute Editor")
        self.setStyleSheet(STYLESHEET)
        self.resize(1280, 800)

        self.session = BatchAttributeSession()
        self.model = AttributeTableModel(self)

        self._editor = None
        self._current: Optional[AggregatedAttribute] = None
        self._channels: Tuple = ()
        self._preview: Optional[PreviewReport] = None
        self._jobs: List[int] = []
        self._last_selection: List[str] = []

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
        root = QtWidgets.QHBoxLayout(self)
        root.setContentsMargins(OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN, OUTER_MARGIN)
        root.setSpacing(COLUMN_SPACING)

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
        container = QtWidgets.QGroupBox("Results")
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

        self.results_label = QtWidgets.QLabel("Nothing searched yet")
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
        group = QtWidgets.QGroupBox("Value")
        layout = QtWidgets.QVBoxLayout(group)
        layout.setContentsMargins(GROUP_INSET, 6, GROUP_INSET, 8)
        layout.setSpacing(ROW_SPACING)

        self.value_hint = QtWidgets.QLabel("Select an attribute above to edit it")
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
            self.scope_panel.set_status(f"Reading the selection failed: {exc}")
            return

        self._last_selection = [
            name for name in SelectionManager.current_selection() if "." not in name
        ]
        self.scope_panel.set_status(self.session.state.describe())
        self._current = None
        self._editor = None
        self._clear_value_area()
        self.details_panel.clear()
        self.technical_panel.clear()
        self.preview_panel.set_message('Set a value, then click "Preview"')
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
        self.model.set_attributes(result.attributes)

        if result.attributes:
            self.results_stack.setCurrentWidget(self.table)
        else:
            self.results_stack.setCurrentWidget(self.empty_state_label)

        if result.scanned_nodes == 0:
            # The most common case: the window just opened and nothing is selected in the viewport
            self.empty_state_label.setText(
                "No nodes scanned yet — select nodes in the viewport"
            )
            self.results_label.setText("")
        elif result.is_empty:
            self.empty_state_label.setText(
                f"No attribute matches (scanned {result.scanned_nodes} nodes)"
            )
            self.results_label.setText("")
        else:
            self.results_label.setText(result.describe())

        self._current = None
        self._editor = None
        self._clear_value_area()
        self.details_panel.clear()
        self.technical_panel.clear()

        if result.attributes:
            self.table.selectRow(0)

    # ------------------------------------------------------------ the selected attribute

    def _on_selection_changed(self, *_args) -> None:
        indexes = self.table.selectionModel().selectedRows()
        if not indexes:
            return
        attribute = self.model.attribute_at(indexes[0].row())
        if attribute is None:
            return
        self._current = attribute
        self.preview_panel.set_message('Set a value, then click "Preview"')
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
            self.details_panel.set_note(f"Validation failed: {exc}")
            self.technical_panel.set_text(f"Validation failed: {exc}")
            return
        if attribute is self._current:
            self.details_panel.set_summary(summary)

    def _clear_value_area(self) -> None:
        while self.value_container_layout.count():
            item = self.value_container_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()
        self.value_hint.setText("Select an attribute above to edit it")
        self._sync_value_area_height()

    def _build_editor(self, attribute: AggregatedAttribute) -> None:
        """Create the value editor for the attribute type."""
        self._clear_value_area()

        if not attribute.definition.supports_editing:
            self.value_hint.setText(
                f"{attribute.type_label} type is not editable yet "
                "(recognition and inspection only)"
            )
            return

        channels = self.session.channels_for(attribute)
        self._channels = channels
        if not channels:
            self.value_hint.setText("This attribute has no editable channels on the current nodes")
            return

        samples = self.session.sample_values(attribute, channels)
        editor = ValueEditorFactory.create(
            attribute.definition, channels, samples, self.value_container
        )
        if editor is None:
            self.value_hint.setText("Could not create an editor for this attribute")
            return

        self._editor = editor
        editor.changed.connect(self._on_value_changed)
        self.value_container_layout.addWidget(editor)
        editor.show()

        reload_callback = getattr(editor, "set_reload_callback", None)
        if callable(reload_callback):
            reload_callback(lambda: self._reload_values(attribute, editor))

        self.value_hint.setText(self._value_hint_text(attribute, channels, samples))
        self._sync_value_area_height()

    def _value_hint_text(self, attribute: AggregatedAttribute, channels, samples) -> str:
        """Hint above the editor: type, channel count, units and the "other types excluded" note."""
        parts = [f"{attribute.type_label}, {attribute.node_count} nodes"]
        if len(channels) > 1:
            parts.append(f"{len(channels)} channels")
        units = [widget for widget in {getattr(c, "unit_type", None) for c in channels} if widget]
        if units:
            parts.append("Values use Maya working units (degrees / centimetres / frames)")
        if not samples:
            parts.append("No current value could be read, please fill it in manually")
        if attribute.other_type_total:
            parts.append(
                f"{attribute.other_type_total} more nodes have this attribute name with a "
                "different type and will be skipped automatically"
            )
        return " · ".join(parts)

    def _reload_values(self, attribute: AggregatedAttribute, editor) -> None:
        """Read the current scene values into the editor again."""
        samples = self.session.sample_values(attribute, self._channels)
        if not samples:
            self.value_hint.setText("Could not read the current value")
            return
        editor.set_values(samples)
        self._on_value_changed()

    def _on_value_changed(self) -> None:
        """A value changed → the preview is invalid → disable "Apply"."""
        self._preview = None
        self.preview_panel.set_message(
            'Values changed — click "Preview" again', level="warning"
        )

    # ------------------------------------------------------------ preview and apply

    def _build_payload(self) -> Tuple[Optional[ValuePayload], List[str]]:
        """Turn the input from the editor into a type-safe payload."""
        if self._editor is None or self._current is None:
            return None, ["Select an attribute to edit first"]

        # A typed but not-yet-committed numeric edit must be committed before
        # reading, otherwise the write would silently use the previous value.
        commit = getattr(self._editor, "commit", None)
        if callable(commit):
            commit()

        values = self._editor.values()
        if not values:
            return None, ["No channels are enabled"]

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
            self.preview_panel.set_message("; ".join(problems), level="error")
            return
        if payload is None:
            self.preview_panel.set_message("Nothing to write", level="warning")
            return

        attribute = self._current
        assert attribute is not None

        def action() -> None:
            report = self.session.preview(attribute, payload)
            self._preview = report
            detail = report.detail_text()
            if report.will_modify == 0:
                self.preview_panel.set_message(
                    "No nodes can be modified:\n"
                    + (report.skip_summary() or "check your filters and scope"),
                    level="warning",
                )
                self.preview_panel.node_list.setPlainText(detail)
                return
            self.preview_panel.set_preview(report.describe(), detail)

        self._run_busy(action)

    def apply_changes(self) -> None:
        """Run the batch modification (the whole batch is a single Undo)."""
        if self._preview is None:
            self.preview_panel.set_message("A preview is required before applying", level="warning")
            return

        payload, problems = self._build_payload()
        if problems or payload is None:
            self.preview_panel.set_message("; ".join(problems) or "Nothing to write", level="error")
            return

        attribute = self._current
        assert attribute is not None

        def action() -> None:
            report: ApplyReport = self.session.apply(attribute, payload)
            self._preview = None
            self.preview_panel.set_report(report.describe())
            self.log_panel.append_log(report.log, self._audit_header(report))
            self.preview_panel.undo_hint.setText(
                "Recorded as a single Undo (Ctrl+Z reverts the whole batch)"
            )
            # Writing may change the lock state; revalidate so the details stay accurate
            QtCore.QTimer.singleShot(0, lambda: self._run_busy(
                lambda: self._validate_current(attribute)))

        self._run_busy(action)

    # ------------------------------------------------------------ audit header

    @staticmethod
    def _audit_header(report: ApplyReport) -> str:
        """Header line of one audit batch: attribute, value, time and counts."""
        counts = [f"{report.succeeded} changed"]
        if report.skipped_count:
            counts.append(f"{report.skipped_count} skipped")
        if report.failed:
            counts.append(f"{report.failed} failed")
        return (f"── {report.attribute_name} · {report.value_repr} · "
                f"{time.strftime('%H:%M:%S')} · {', '.join(counts)} ──")

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

            self.scope_panel.set_status(f"Operation failed: {exc}")
            self.log_panel.append(f"[ERROR] {exc}\n{traceback.format_exc()}")
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()
