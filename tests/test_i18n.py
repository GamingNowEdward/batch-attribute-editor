"""Localization tests: manager, catalogs, persistence, Core texts and (GUI) UI switching."""

from __future__ import annotations

import os
import re
import string
import tempfile
import unittest

import i18n
from i18n import TranslationManager
from i18n.en import TRANSLATIONS as EN
from i18n.zh_cn import TRANSLATIONS as ZH

try:
    from ui.qt import QtWidgets

    _QT_ERROR = ""
except ImportError as exc:  # pragma: no cover
    QtWidgets = None
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

#: Every noun rendered through plural() by Core / UI code
_PLURAL_NOUNS = (
    "node",
    "channel",
    "root node",
    "attribute",
    "attribute instance",
    "transform",
    "shape",
    "intermediate",
    "DG node",
    "type definition",
    "more change",
    "more skipped node",
)


class TranslationManagerTest(unittest.TestCase):
    """Language switching, fallback and formatting (independent manager instances)."""

    def setUp(self) -> None:
        self.manager = TranslationManager()

    def test_default_language_is_english(self) -> None:
        self.assertEqual(self.manager.language, "en")
        self.assertEqual(self.manager.translate("status.locked"), "Locked")

    def test_switch_english_to_chinese_and_back(self) -> None:
        self.assertTrue(self.manager.set_language("zh_CN"))
        self.assertEqual(self.manager.language, "zh_CN")
        self.assertEqual(self.manager.translate("status.locked"), "已锁定")
        self.assertTrue(self.manager.set_language("en"))
        self.assertEqual(self.manager.translate("status.locked"), "Locked")

    def test_switching_to_the_same_language_reports_no_change(self) -> None:
        self.assertFalse(self.manager.set_language("en"))
        self.manager.set_language("zh_CN")
        self.assertFalse(self.manager.set_language("zh_CN"))

    def test_unknown_language_falls_back_to_english(self) -> None:
        self.manager.set_language("zh_CN")
        self.assertTrue(self.manager.set_language("fr_FR"))
        self.assertEqual(self.manager.language, "en")
        self.assertEqual(self.manager.translate("status.locked"), "Locked")
        self.assertEqual(self.manager.translate("window.title"), "Batch Attribute Editor")

    def test_missing_translation_falls_back_to_english(self) -> None:
        manager = TranslationManager(catalogs={"zh_CN": {"window.title": "标题"}})
        manager.set_language("zh_CN")
        self.assertEqual(manager.translate("window.title"), "标题")
        self.assertEqual(manager.translate("status.locked"), "Locked")

    def test_unknown_key_returns_the_key(self) -> None:
        self.assertEqual(self.manager.translate("no.such.key"), "no.such.key")
        self.manager.set_language("zh_CN")
        self.assertEqual(self.manager.translate("no.such.key"), "no.such.key")

    def test_language_aliases_are_normalized(self) -> None:
        self.manager.set_language("zh-cn")
        self.assertEqual(self.manager.language, "zh_CN")
        self.manager.set_language("zh")
        self.assertEqual(self.manager.language, "zh_CN")
        self.manager.set_language("EN_us")
        self.assertEqual(self.manager.language, "en")

    def test_format_parameters(self) -> None:
        self.assertEqual(
            self.manager.translate("value.hint.type_nodes", type="Double3", count=4),
            "Double3, 4 nodes",
        )
        self.manager.set_language("zh_CN")
        self.assertEqual(
            self.manager.translate("value.hint.type_nodes", type="Double3", count=4),
            "Double3，4 个节点",
        )

    def test_broken_placeholders_do_not_raise(self) -> None:
        manager = TranslationManager(catalogs={"zh_CN": {"x.broken": "值 {value}"}})
        manager.set_language("zh_CN")
        self.assertEqual(manager.translate("x.broken", other=1), "值 {value}")

    def test_plural_renderings(self) -> None:
        self.assertEqual(self.manager.plural(1, "node"), "1 node")
        self.assertEqual(self.manager.plural(2, "node"), "2 nodes")
        self.assertEqual(self.manager.plural(2, "intermediate", "intermediates"),
                         "2 intermediates")
        self.manager.set_language("zh_CN")
        self.assertEqual(self.manager.plural(1, "node"), "1 个节点")
        self.assertEqual(self.manager.plural(2, "node"), "2 个节点")
        self.assertEqual(self.manager.plural(3, "root node"), "3 个根节点")

    def test_plural_unknown_noun_falls_back_to_english(self) -> None:
        self.assertEqual(self.manager.plural(2, "widget"), "2 widgets")
        self.manager.set_language("zh_CN")
        self.assertEqual(self.manager.plural(2, "widget"), "2 widgets")


def _placeholders(text: str) -> set:
    """The ``{named}`` placeholders used by a template."""
    return {name for _literal, name, _spec, _conv in string.Formatter().parse(text) if name}


class TranslationCatalogTest(unittest.TestCase):
    """English is the reference language: the catalogs must stay complete."""

    def test_chinese_has_exactly_the_english_keys(self) -> None:
        missing = set(EN) - set(ZH)
        extra = set(ZH) - set(EN)
        self.assertEqual(missing, set(), f"Missing zh_CN translations: {sorted(missing)}")
        self.assertEqual(extra, set(), f"Unexpected zh_CN keys: {sorted(extra)}")
        self.assertEqual(len(EN), len(ZH))

    def test_no_empty_translations(self) -> None:
        for name, catalog in (("en", EN), ("zh_CN", ZH)):
            for key, text in catalog.items():
                with self.subTest(language=name, key=key):
                    self.assertTrue(str(text).strip(), f"{name} translation is empty")

    def test_placeholders_match_between_languages(self) -> None:
        for key, text in EN.items():
            with self.subTest(key=key):
                self.assertEqual(_placeholders(text), _placeholders(ZH[key]))

    def test_plural_nouns_are_complete(self) -> None:
        for noun in _PLURAL_NOUNS:
            key_base = "counts." + noun.lower().replace(" ", "_")
            for suffix in ("one", "other"):
                with self.subTest(noun=noun, suffix=suffix):
                    self.assertIn(f"{key_base}.{suffix}", EN)
                    self.assertIn(f"{key_base}.{suffix}", ZH)

    def test_dynamic_key_families_resolve(self) -> None:
        try:
            from core.compatibility import ValidationStatus
            from core.search import MatchMode
            from core.traversal import TraversalScope
        except ImportError as exc:  # pragma: no cover
            self.skipTest(f"Core needs Maya: {exc}")

        for scope in TraversalScope:
            self.assertIn(f"scope.option.{scope.value}", EN)
        for mode in MatchMode:
            self.assertIn(f"search.mode.{mode.value}", EN)
            self.assertIn(f"search.mode.{mode.value}.tooltip", EN)
        for status in ValidationStatus:
            self.assertIn(f"status.{status.value}", EN)

    def test_every_literal_key_used_in_source_exists(self) -> None:
        """Every static ``tr("key")`` in the code must exist in the catalog."""
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        pattern = re.compile(r"\btr\(\s*[\"']([A-Za-z0-9_.]+)[\"']")
        paths = []
        for folder in ("core", "ui", "utils"):
            for base, _dirs, names in os.walk(os.path.join(root, folder)):
                paths.extend(
                    os.path.join(base, name) for name in names if name.endswith(".py")
                )
        self.assertTrue(paths)
        for path in paths:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            for key in pattern.findall(text):
                with self.subTest(source=os.path.basename(path), key=key):
                    self.assertIn(key, EN, f"{key} used in {path} is missing from i18n.en")

    def test_english_reference_texts_are_unchanged(self) -> None:
        """The historical English strings the existing tests rely on."""
        expected = {
            "window.title": "Batch Attribute Editor",
            "status.locked": "Locked",
            "status.connected": "Connected",
            "status.missing": "Attribute missing",
            "status.type_mismatch": "Type mismatch",
            "preview.detail.will_modify": "── Will modify ──",
            "preview.detail.skipped": "── Skipped ──",
            "preview.skipped_fallback": "skipped",
            "apply.describe.succeeded": "Succeeded:{count}",
            "apply.describe.failed": "  Failed:{count}",
            "preview.describe.main": "Will modify {nodes} ({channels}), skip {skipped}",
            "search.result.describe": (
                "Matched {attributes} / {instances} (scanned {nodes}, {ms} ms)"
            ),
            "selection.empty": (
                "No nodes selected — select something in the viewport"
            ),
            "session.not_selected": "not selected",
            "unit.degrees": "Degrees",
            "counts.node.one": "1 node",
            "counts.node.other": "{count} nodes",
        }
        for key, text in expected.items():
            with self.subTest(key=key):
                self.assertEqual(EN[key], text)


class _FakeSettings:
    """Minimal QSettings stand-in (records values in memory)."""

    def __init__(self, values=None) -> None:
        self.values = dict(values or {})
        self.synced = 0

    def value(self, key, default=None):
        return self.values.get(key, default)

    def setValue(self, key, value) -> None:  # noqa: N802 - Qt naming
        self.values[key] = value

    def sync(self) -> None:
        self.synced += 1


class _BrokenSettings:
    """A store whose every operation fails."""

    def value(self, key, default=None):
        raise RuntimeError("store unavailable")

    def setValue(self, key, value) -> None:  # noqa: N802
        raise RuntimeError("store unavailable")

    def sync(self) -> None:
        raise RuntimeError("store unavailable")


class LanguageSettingsTest(unittest.TestCase):
    """Persistence: first launch, save/reload and failing stores."""

    def test_first_launch_is_english(self) -> None:
        from ui.settings import LanguageSettings

        settings = LanguageSettings(_FakeSettings())
        self.assertEqual(settings.load(), "en")

    def test_save_chinese_then_reload(self) -> None:
        from ui.settings import LanguageSettings

        store = _FakeSettings()
        LanguageSettings(store).save("zh_CN")
        self.assertEqual(LanguageSettings(store).load(), "zh_CN")
        self.assertGreaterEqual(store.synced, 1)

    def test_save_english_then_reload(self) -> None:
        from ui.settings import LanguageSettings

        store = _FakeSettings({"language": "zh_CN"})
        LanguageSettings(store).save("en")
        self.assertEqual(LanguageSettings(store).load(), "en")

    def test_blank_value_falls_back_to_english(self) -> None:
        from ui.settings import LanguageSettings

        settings = LanguageSettings(_FakeSettings({"language": "   "}))
        self.assertEqual(settings.load(), "en")

    def test_broken_store_never_raises(self) -> None:
        from ui.settings import LanguageSettings

        settings = LanguageSettings(_BrokenSettings())
        self.assertEqual(settings.load(), "en")
        settings.save("zh_CN")

    def test_real_qsettings_roundtrip_in_temporary_ini(self) -> None:
        """The QSettings integration itself (isolated in a temp file)."""
        try:
            from ui.qt import QtCore
        except ImportError:  # pragma: no cover
            self.skipTest(f"Qt is not available: {_QT_ERROR}")
        from ui.settings import LanguageSettings

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "language-settings.ini")
            first = QtCore.QSettings(path, QtCore.QSettings.IniFormat)
            store = LanguageSettings(first)
            self.assertEqual(store.load(), "en")
            store.save("zh_CN")

            second = QtCore.QSettings(path, QtCore.QSettings.IniFormat)
            second.sync()
            self.assertEqual(LanguageSettings(second).load(), "zh_CN")


class CoreLocalizationTest(unittest.TestCase):
    """Core report texts follow the active language and restore exactly."""

    def setUp(self) -> None:
        self._original = i18n.get_language()
        i18n.set_language("en")

    def tearDown(self) -> None:
        i18n.set_language(self._original)

    def _require_core(self) -> None:
        try:
            from core.compatibility import ValidationStatus, status_label  # noqa: F401
            from core.results import ApplyItemResult, ApplyReport, PreviewReport  # noqa: F401
        except ImportError as exc:  # pragma: no cover
            self.skipTest(f"Core needs Maya: {exc}")

    def test_status_label_follows_language(self) -> None:
        self._require_core()
        from core.compatibility import ValidationStatus, status_label

        self.assertEqual(status_label(ValidationStatus.LOCKED), "Locked")
        i18n.set_language("zh_CN")
        self.assertEqual(status_label(ValidationStatus.LOCKED), "已锁定")
        self.assertEqual(status_label(ValidationStatus.CONNECTED), "存在连接")
        self.assertEqual(status_label(ValidationStatus.TYPE_MISMATCH), "类型不匹配")

    def test_preview_report_texts_follow_language(self) -> None:
        self._require_core()
        from core.compatibility import ValidationStatus
        from core.results import PreviewReport

        report = PreviewReport(
            attribute_name="visibility",
            type_label="Boolean",
            counts={ValidationStatus.LOCKED: 2, ValidationStatus.CONNECTED: 1},
        )
        english = report.describe()
        self.assertTrue(english.startswith("Will modify 0 nodes (0 channels), skip 0"))
        self.assertIn("Skip reasons: 2 Locked, 1 Connected", english)

        i18n.set_language("zh_CN")
        chinese = report.describe()
        self.assertIn("将修改", chinese)
        self.assertIn("跳过原因：", chinese)
        self.assertIn("已锁定", chinese)

        i18n.set_language("en")
        self.assertEqual(report.describe(), english)

    def test_apply_report_texts_follow_language(self) -> None:
        self._require_core()
        from core.results import ApplyItemResult, ApplyReport

        report = ApplyReport(attribute_name="visibility", type_label="Boolean")
        report.items.append(
            ApplyItemResult(
                node_name="CubeA",
                channel_label="Value",
                target="CubeA.visibility",
                success=True,
                value=True,
            )
        )
        english = report.describe()
        self.assertIn("Succeeded:1", english)

        i18n.set_language("zh_CN")
        self.assertIn("成功：1", report.describe())

        i18n.set_language("en")
        self.assertEqual(report.describe(), english)

    def test_plural_helper_follows_language(self) -> None:
        from utils.logging_utils import plural

        self.assertEqual(plural(2, "node"), "2 nodes")
        i18n.set_language("zh_CN")
        self.assertEqual(plural(2, "node"), "2 个节点")
        i18n.set_language("en")
        self.assertEqual(plural(1, "node"), "1 node")


@unittest.skipUnless(_gui_available(), _GUI_SKIP)
class UILanguageTest(unittest.TestCase):
    """The language selector updates the open window without recreating it."""

    def setUp(self) -> None:
        self._original = i18n.get_language()
        i18n.set_language("en")

    def tearDown(self) -> None:
        i18n.set_language(self._original)

    def test_switch_to_chinese_and_back(self) -> None:
        from ui.main_window import BatchAttributeEditorWindow
        from ui.settings import LanguageSettings

        window = BatchAttributeEditorWindow()
        window._language_settings = LanguageSettings(_FakeSettings())
        try:
            self.assertEqual(window.windowTitle(), "Batch Attribute Editor")
            panels = (window.scope_panel, window.search_panel, window.preview_panel)
            groups = (window.value_group, window.results_group)

            chinese_index = window.language_combo.findData("zh_CN")
            self.assertGreaterEqual(chinese_index, 0)
            window.language_combo.setCurrentIndex(chinese_index)

            self.assertEqual(window.windowTitle(), "批量属性编辑器")
            self.assertIn("应用", window.preview_panel.apply_button.text())
            self.assertIn("预览", window.preview_panel.preview_button.text())

            # Nothing was recreated: the very same widget instances remain
            self.assertIs(window.scope_panel, panels[0])
            self.assertIs(window.search_panel, panels[1])
            self.assertIs(window.preview_panel, panels[2])
            self.assertIs(window.value_group, groups[0])
            self.assertIs(window.results_group, groups[1])

            english_index = window.language_combo.findData("en")
            window.language_combo.setCurrentIndex(english_index)
            self.assertEqual(window.windowTitle(), "Batch Attribute Editor")
            self.assertEqual(window.preview_panel.apply_button.text(), "Apply")
        finally:
            window.teardown()
            window.deleteLater()

    # ------------------------------------------------- audit log language freeze

    @staticmethod
    def _log_text(panel) -> str:
        """The rendered log with non-breaking spaces normalised."""
        return panel.text.toPlainText().replace("\u00a0", " ")

    @staticmethod
    def _entry(message: str, detail: str):
        from utils.logging_utils import LogEntry, LogLevel

        return LogEntry(level=LogLevel.INFO, message=message, detail=detail)

    def test_english_audit_batch_keeps_english_after_switching_to_chinese(self) -> None:
        """Scenario 1: an English batch keeps its 'detail:' prefix in Chinese mode."""
        from utils.logging_utils import OperationLog
        from ui.panels import LogPanel

        panel = LogPanel()
        try:
            log = OperationLog(title="batch")
            log.entries.append(self._entry("EN-MESSAGE", "EN-DETAIL"))
            panel.append_log(log, "── EN-HEADER ──")

            i18n.set_language("zh_CN")
            panel.refresh()
            text = self._log_text(panel)

            self.assertIn("detail: EN-DETAIL", text)
            self.assertNotIn("详情：", text)
            self.assertIn("EN-MESSAGE", text)
        finally:
            panel.deleteLater()

    def test_chinese_audit_batch_keeps_chinese_after_switching_to_english(self) -> None:
        """Scenario 2: a Chinese batch keeps its '详情：' prefix in English mode."""
        from utils.logging_utils import OperationLog
        from ui.panels import LogPanel

        panel = LogPanel()
        try:
            i18n.set_language("zh_CN")
            log = OperationLog(title="batch")
            log.entries.append(self._entry("ZH-MESSAGE", "ZH-DETAIL"))
            panel.append_log(log, "── ZH-HEADER ──")

            i18n.set_language("en")
            panel.refresh()
            text = self._log_text(panel)

            self.assertIn("详情： ZH-DETAIL", text)
            self.assertNotIn("detail:", text)
            self.assertIn("ZH-MESSAGE", text)
        finally:
            panel.deleteLater()

    def test_new_audit_batch_uses_the_language_at_creation_time(self) -> None:
        """Scenario 3: mixed history - each batch keeps the language it was written in."""
        from utils.logging_utils import OperationLog
        from ui.panels import LogPanel

        panel = LogPanel()
        try:
            english = OperationLog(title="batch")
            english.entries.append(self._entry("EN-MESSAGE", "EN-DETAIL"))
            panel.append_log(english, "── EN-HEADER ──")

            i18n.set_language("zh_CN")
            chinese = OperationLog(title="batch")
            chinese.entries.append(self._entry("ZH-MESSAGE", "ZH-DETAIL"))
            panel.append_log(chinese, "── ZH-HEADER ──")

            i18n.set_language("en")
            panel.refresh()
            text = self._log_text(panel)

            self.assertIn("detail: EN-DETAIL", text)
            self.assertIn("详情： ZH-DETAIL", text)
            self.assertNotIn("详情： EN-DETAIL", text)
            self.assertNotIn("detail: ZH-DETAIL", text)
        finally:
            panel.deleteLater()
