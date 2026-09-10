"""UI smoke tests.

The full UI interaction cannot be automated, but the **construction** process
can be verified: import errors, factory dispatch errors, wrong channel widget
types and wrong model column definitions all surface here.

Environment limitation (measured): a **QApplication cannot be created** under
``mayapy`` / ``standalone`` (attempting it makes the process exit fatally), so
every test that needs a QWidget runs only in a real Maya GUI session; the pure
data model tests run in any environment.
"""

from __future__ import annotations

import unittest

from core.attributes import AttributeScanner
from core.batch_setter import ValuePayload
from core.search import SearchEngine
from core.selection import SelectionManager
from core.traversal import DagTraversal, TraversalScope
from core.types import AttributeKind, EditorKind
from tests import support

try:
    from ui.qt import QT_API, QtWidgets

    _QT_ERROR = ""
except ImportError as exc:  # pragma: no cover
    QtWidgets = None
    QT_API = ""
    _QT_ERROR = str(exc)


def _gui_available() -> bool:
    """Whether the current session has a usable Qt GUI (batch / standalone do not)."""
    if QtWidgets is None:
        return False
    try:
        from maya import cmds

        return not cmds.about(batch=True)
    except Exception:  # noqa: BLE001
        return False


_GUI_SKIP = (
    "needs a real Maya GUI session (a QApplication cannot be created under "
    "batch/standalone, and creating one makes the process exit)"
)


class UIImportTest(unittest.TestCase):
    """Import and registry completeness of the UI modules.

    These checks need no QApplication, so they run under mayapy too - they catch
    syntax errors, wrong import paths, misspelled Qt API names (for example the
    different ``QAction`` location in PySide2/PySide6) and missing factory
    registry entries.
    """

    MODULES = (
        "ui.qt",
        "ui.styles",
        "ui.attribute_model",
        "ui.panels",
        "ui.editors.base",
        "ui.editors.channel_widgets",
        "ui.editors.value_editors",
        "ui.editors.factory",
        "ui.main_window",
        "main",
    )

    def test_all_ui_modules_import(self) -> None:
        """Every UI module can be imported (no errors in module-level code or class definitions)."""
        import importlib

        for name in self.MODULES:
            with self.subTest(module=name):
                importlib.import_module(name)

    def test_factory_registry_covers_every_editor_kind(self) -> None:
        """The editor factory covers every editable EditorKind."""
        from ui.editors.factory import ValueEditorFactory

        for kind in EditorKind:
            if kind is EditorKind.NONE:
                continue
            with self.subTest(kind=kind):
                self.assertIn(kind, ValueEditorFactory._registry,
                              f"{kind} has no registered editor")

    def test_channel_widget_registry_covers_editable_kinds(self) -> None:
        """The channel widget registry covers every type that needs an input widget."""
        from ui.editors.channel_widgets import _WIDGET_REGISTRY

        for kind in (EditorKind.FLOAT, EditorKind.INT, EditorKind.BOOL,
                     EditorKind.STRING, EditorKind.ENUM, EditorKind.UNIT,
                     EditorKind.COLOR3, EditorKind.VECTOR3):
            with self.subTest(kind=kind):
                self.assertIn(kind, _WIDGET_REGISTRY)

    def test_editor_class_selection_by_attribute_type(self) -> None:
        """The editor class chosen for each attribute type is the expected one."""
        from core.types import AttributeDefinition
        from ui.editors.factory import ValueEditorFactory
        from ui.editors.value_editors import (
            ColorValueEditor,
            ScalarValueEditor,
            VectorValueEditor,
        )

        color = AttributeDefinition(name="color", short_name="color",
                                    kind=AttributeKind.COLOR3, is_color=True)
        self.assertIs(ValueEditorFactory.editor_class_for(color), ColorValueEditor)

        vector = AttributeDefinition(name="translate", short_name="t",
                                     kind=AttributeKind.VECTOR3, api_type="kAttribute3Double")
        self.assertIs(ValueEditorFactory.editor_class_for(vector), VectorValueEditor)

        scalar = AttributeDefinition(name="visibility", short_name="v", kind=AttributeKind.BOOL)
        self.assertIs(ValueEditorFactory.editor_class_for(scalar), ScalarValueEditor)


@unittest.skipUnless(_gui_available(), _GUI_SKIP)
class UIEditorTest(unittest.TestCase):
    """Construction and value handling of value editors and channel widgets."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = support.build_scene()
        cls.engine = SearchEngine(AttributeScanner())
        result = SelectionManager.resolve([cls.scene["root"]])
        cls.records = DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )

    def group(self, pattern: str, name: str):
        found = self.engine.search(self.records, pattern)
        for item in found.attributes:
            if item.name == name:
                return item
        self.fail(f"Attribute {name} not found")

    def build_editor(self, pattern: str, name: str):
        from core.session import BatchAttributeSession
        from ui.editors.factory import ValueEditorFactory

        group = self.group(pattern, name)
        session = BatchAttributeSession()
        session.records = self.records
        channels = session.channels_for(group)
        samples = session.sample_values(group, channels)
        editor = ValueEditorFactory.create(group.definition, channels, samples)
        self.assertIsNotNone(editor)
        return editor, channels

    def test_boolean_editor_uses_checkbox(self) -> None:
        """Boolean produces a checkbox editor and yields a boolean value."""
        editor, _channels = self.build_editor("visibility", "visibility")
        values = editor.values()
        self.assertEqual(len(values), 1)
        self.assertIsInstance(list(values.values())[0], bool)

    def test_integer_editor_validates_integer(self) -> None:
        """Invalid text in an Integer field must report a validation error instead of silently truncating."""
        editor, channels = self.build_editor("customInt", "customInt")
        widget = editor.channel_widget(channels[0].key)
        widget.set_value("abc")
        self.assertTrue(editor.invalid_channels(), "Invalid integer input should be flagged")

        widget.set_value("7")
        self.assertFalse(editor.invalid_channels())
        self.assertEqual(editor.values()[channels[0].key], 7)

    def test_string_editor_keeps_text(self) -> None:
        """The String editor yields a string and does not convert it to a number."""
        editor, channels = self.build_editor("customString", "customString")
        editor.set_values({channels[0].key: "hello"})
        self.assertEqual(editor.values()[channels[0].key], "hello")

    def test_enum_editor_lists_fields(self) -> None:
        """Enum produces a combo box whose value is Maya's enum index."""
        editor, channels = self.build_editor("customEnum", "customEnum")
        self.assertIsInstance(channels[0].editor_kind, EditorKind)
        self.assertEqual(channels[0].enum_fields[0][0], "Off")
        editor.set_values({channels[0].key: 2})
        self.assertEqual(editor.values()[channels[0].key], 2)

    def test_vector_editor_has_three_channels(self) -> None:
        """Double3 produces three channels X/Y/Z and only one of them can be checked."""
        editor, channels = self.build_editor("translate", "translate")
        self.assertEqual([channel.label for channel in channels], ["X", "Y", "Z"])
        self.assertEqual(len(editor.values()), 3)

        widget = editor.channel_widget(channels[1].key)
        widget.set_enabled_channel(False)
        values = editor.values()
        self.assertEqual(len(values), 2, "An unchecked channel must not take part in the write")

    def test_color_editor_builds_rgb_and_picker(self) -> None:
        """Color3 produces R/G/B channels and offers a colour picker."""
        from ui.editors.value_editors import ColorValueEditor

        editor, channels = self.build_editor("overrideColorRGB", "overrideColorRGB")
        self.assertIsInstance(editor, ColorValueEditor)
        self.assertEqual([channel.label for channel in channels], ["R", "G", "B"])

        editor.set_rgb((1.0, 0.5, 0.25))
        values = editor.values()
        self.assertAlmostEqual(values[channels[0].key], 1.0, places=5)
        self.assertAlmostEqual(values[channels[2].key], 0.25, places=5)

    def test_color_editor_does_not_clamp(self) -> None:
        """The colour editor does not clamp input to 0-1 on its own."""
        editor, channels = self.build_editor("overrideColorRGB", "overrideColorRGB")
        editor.set_rgb((2.5, -0.5, 0.0))
        values = editor.values()
        self.assertAlmostEqual(values[channels[0].key], 2.5, places=5)
        self.assertAlmostEqual(values[channels[1].key], -0.5, places=5)

    def test_multi_attribute_editor_has_element_rows(self) -> None:
        """A Multi attribute produces one channel per already existing array element."""
        editor, channels = self.build_editor("customMulti", "customMulti")
        labels = [channel.display_label for channel in channels]
        self.assertIn("[0] Value", labels)
        self.assertIn("[1] Value", labels)
        self.assertEqual(len(editor.values()), len(channels))

    def test_unit_editor_reports_working_unit(self) -> None:
        """The channel widget of a unit attribute hints at the working unit."""
        editor, channels = self.build_editor("customAngle", "customAngle")
        widget = editor.channel_widget(channels[0].key)
        self.assertEqual(widget.unit_hint(), "Degrees")
        self.assertIn("Degrees", widget.toolTip())

    def test_editor_values_feed_payload(self) -> None:
        """Values produced by an editor can be fed straight into a ValuePayload (type safe)."""
        editor, channels = self.build_editor("customFloat", "customFloat")
        editor.set_values({channels[0].key: 1.25})
        payload = ValuePayload()
        for key, value in editor.values().items():
            channel = [item for item in channels if item.key == key][0]
            payload.set_raw(channel, value)
        self.assertEqual(payload.get(channels[0]), 1.25)


class UIModelTest(unittest.TestCase):
    """The result table model (pure data, needs no QApplication, so it runs under mayapy too)."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = support.build_scene()

    def test_model_exposes_aggregated_rows(self) -> None:
        """The model's row count matches the aggregated search result."""
        from ui.attribute_model import AttributeTableModel

        engine = SearchEngine(AttributeScanner())
        result = SelectionManager.resolve([self.scene["root"]])
        records = DagTraversal.collect(
            [record.node for record in result.roots],
            TraversalScope.SELECTION_AND_DESCENDANTS,
        )
        found = engine.search(records, "customFloat")

        model = AttributeTableModel()
        model.set_attributes(found.attributes)
        self.assertEqual(model.rowCount(), len(found.attributes))
        self.assertEqual(model.columnCount(), len(AttributeTableModel.HEADERS))

        index = model.index(0, 0)
        self.assertEqual(model.data(index), found.attributes[0].display_name)
        self.assertEqual(model.data(model.index(0, 1)), found.attributes[0].type_label)
        self.assertIsInstance(model.data(model.index(0, 2)), int)

    def test_model_handles_empty_result(self) -> None:
        """An empty result must not crash."""
        from ui.attribute_model import AttributeTableModel

        model = AttributeTableModel()
        model.set_attributes([])
        self.assertEqual(model.rowCount(), 0)
        self.assertIsNone(model.attribute_at(0))


@unittest.skipUnless(_gui_available(), _GUI_SKIP)
class UIPanelTest(unittest.TestCase):
    """Panel construction."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.scene = support.build_scene()

    def test_panels_construct(self) -> None:
        """Every section can be constructed independently."""
        from ui.panels import (
            DetailsPanel,
            LogPanel,
            PreviewPanel,
            ScopePanel,
            SearchPanel,
        )

        scope = ScopePanel()
        self.assertIsInstance(scope.current_scope(), TraversalScope)

        search = SearchPanel()
        self.assertEqual(search.pattern(), "")
        self.assertTrue(search.filters().hide_unsupported)

        details = DetailsPanel()
        details.clear()

        preview = PreviewPanel()
        self.assertFalse(preview.apply_button.isEnabled(), "Apply must be disabled before a preview exists")

        log = LogPanel()
        log.append("hello")
        self.assertIn("hello", log.text.toPlainText())

    def test_main_window_constructs_and_searches(self) -> None:
        """The main window can be constructed, can scan and can search (without being shown)."""
        try:
            from ui.main_window import BatchAttributeEditorWindow
        except ImportError as exc:  # pragma: no cover
            self.skipTest(f"The main window needs Maya GUI modules: {exc}")

        cmds = support.ensure_maya()
        cmds.select(self.scene["root"], replace=True)

        window = BatchAttributeEditorWindow()
        try:
            self.assertGreater(window.session.state.node_count, 5,
                               "Opening the window should scan the current selection automatically")
            window.search_panel.pattern_edit.setText("visibility")
            window.run_search()
            self.assertGreater(window.model.rowCount(), 0)

            window.table.selectRow(0)
            self.assertIsNotNone(window._current)
            self.assertIsNotNone(window._editor, "Selecting an attribute should create an editor")

            # applying is not allowed before a preview exists
            window.apply_changes()
            self.assertIsNone(window._preview)
        finally:
            window.teardown()
            window.deleteLater()
            cmds.select(clear=True)


if __name__ == "__main__":
    unittest.main()
