**English** | [中文](CHANGELOG.zh.md)

# Changelog

## 2026-09-14

### Fixed

- `ui/panels.py`: the `SearchPanel` filter checkboxes now connect their `toggled` signals only after
  all of them exist — previously `setChecked(True)` during construction emitted `toggled` before the
  remaining checkboxes were created (an `AttributeError` that PySide printed but swallowed)
- `ui/panels.py`: the raw `| 0x1` text-interaction mask was replaced with
  `Qt.TextSelectableByMouse`, so the window also constructs under the strict PySide6 / Qt 6 enums

### Added

- **Bilingual UI (English / 中文)** with a `Language:` selector in the top-right corner of the
  window: English is the default; switching is immediate (no Maya restart) and refreshes every
  panel in place without recreating widgets; the choice is persisted with `QSettings` and restored
  at the next launch (first launch defaults to English)
- New top-level `i18n/` package (pure Python, no Qt / Maya dependency, used by both Core and UI):
  `manager.py` (catalog lookup, English fallback, `{param}` formatting, `plural()`), `en.py` (the
  English reference catalog, byte-identical to the previous literals) and `zh_cn.py` (Simplified
  Chinese; its key set is enforced to match the English one by a test)
- `ui/settings.py`: `LanguageSettings` — a small QSettings wrapper with an injectable backend
- `tests/test_i18n.py`: 29 tests — manager switching / fallback / formatting / plural, catalog key
  and placeholder parity, a source scan for literal `tr("...")` keys, persistence through fake and
  real QSettings backends, Core report texts, and a GUI language-switch test

### Changed

- All user-visible strings now go through `i18n.tr()` / `i18n.plural()`: window title, section
  titles, buttons, tooltips, placeholders, filters, status lines, Attribute Details, Results table
  headers, Technical Details placeholders, Preview / Apply reports, batch-write and coercion error
  messages, and the audit header. The English catalog reproduces the previous literals exactly, so
  the existing English assertions and behaviour are unchanged
- Language switching replays the window's dynamic state (selection status, search summary / empty
  state, selected-attribute details and validation, the currently displayed Preview / Apply report,
  the value hint) and calls `retranslate()` on existing editors; audit-log entries keep the language
  they were written in
- Maya data is deliberately **not** translated: node / attribute / plug names, enum field values,
  type labels (`Float`, `Double3`, …), `definition.describe()` metadata and exception text stay
  as-is
- `bootstrap.TOP_LEVEL_MODULES` now includes `i18n`, so the same-name module take-over and
  `reload_and_launch()` cover the new package

### Documentation

- README / ARCHITECTURE / USAGE / INSTALL / LIMITATIONS (en + zh) document the localization
  architecture, the language selector, persistence and how to reset it, what is translated versus
  Maya data, and the localization limitations (audit-log language, raw validation errors, English
  type labels)
- Test count refreshed to **171** (13 GUI tests are skipped in batch mode) in README, INSTALL and
  LIMITATIONS (en + zh)

## 2026-09-11

### Fixed

- **The "Hide compound children" search filter now actually works**: `AttributeDefinition` gained
  `is_compound_child` (read via `MPlug.isChild`) and `SearchFilters.accepts_definition` drops child
  attributes such as `translateX` / `customVectorX` while keeping their parent, as `docs/USAGE.md`
  always described; covered by two new tests (type resolution + search)
- **Startup no longer fails when another flat-layout tool owns `core` / `ui` in the same Maya
  session**: `bootstrap.release_conflicting_modules()` now evicts foreign top-level modules **and
  their cached submodules** — a stale foreign `core.results` used to shadow this project's imports
  after a take-over

### Refactored

- `bootstrap.ensure_on_path()` always moves the project root to the **front** of `sys.path` (not
  only inserts it when missing), so `core` / `ui` resolve to this project even when another
  flat-layout tool prepended its own root earlier
- Deferred `core` / `ui` imports moved to module top (kept: the `base` ↔ `channel_widgets` cycle
  and the intentional UI lazy-load in `main.py`)

### Added

- Initial release (`main.__version__` 1.0.0): batch attribute discovery & editing for Maya —
  recursive hierarchy traversal (incl. shapes), search by attribute name, real type resolution,
  compatibility validation (Locked / Connected / Missing / type mismatch), type-aware editors,
  preview + batch writing, and one Undo per Apply
- `core` / `ui` / `utils` package layout, the `mayapy` test suite (136 tests at the time),
  `tools/selfcheck.py`, the one-click `copy_launch.bat` launcher, and README + INSTALL / USAGE /
  ARCHITECTURE / LIMITATIONS docs (en + zh)
- `LICENSE`: the project is released under the MIT License
- `docs/CHANGELOG.md` and `docs/CHANGELOG.zh.md` to record notable changes
- `AttributeDefinition.is_channel_box`, read via `MFnAttribute.channelBox`, plus test coverage for
  the channelBox case (created through the OpenMaya API, because `addAttr` has no `channelBox` flag)
- UI: the match-mode drop-down items carry tooltips explaining each mode

### Changed

- The "Keyable only" filter now keeps attributes that are keyable **or** shown in the Channel Box
  (Arnold reports `aiExposure` as `keyable=False`, `channelBox=True`, and such attributes can be
  keyframed from the Channel Box); the filter is checked by default and the tooltip / USAGE were
  updated accordingly

### Documentation

- README quick start now uses the **`copy_launch.bat`** method instead of the hand-typed
  `sys.path.insert(...)` + `main.launch()` snippet: double-click the script in the project root,
  paste the copied command (it already carries this folder's absolute path) into Maya's Script
  Editor and press Enter; the command calls `main.reload_and_launch()`, which discards this
  project's cached modules first, so edits take effect without restarting Maya. Matches
  [`INSTALL.md`](INSTALL.md) option A (`README.md` / `README.zh.md`)
- README / ARCHITECTURE / INSTALL (en + zh) document the two-way take-over contract ("last launched
  tool wins") and coexistence with `materialConvert`
- `docs/USAGE.md` / `USAGE.zh.md`: expanded the Attribute Search reference — match-mode notes and a
  per-filter explanation (definition-level vs per-node validation, defaults, and the all-nodes rule
  for Locked / Connected); the match-mode table now uses examples that distinguish Contains from
  Prefix and states their nesting (Exact ⊆ Prefix ⊆ Contains)
- Chinese docs terminology: project-owned UI / feature names are now written in Chinese with the
  English label on first mention (README.zh, USAGE.zh, INSTALL.zh, ARCHITECTURE.zh, LIMITATIONS.zh);
  the ASCII UI mock and program output stay English
- Documented test count refreshed from the stale 136 to the actual **142** (12 widget tests are
  skipped in batch mode): README, INSTALL and LIMITATIONS (en + zh)
