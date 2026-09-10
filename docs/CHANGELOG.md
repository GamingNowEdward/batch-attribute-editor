**English** | [中文](CHANGELOG.zh.md)

# Changelog

All notable changes to this project are documented in this file.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); until the first
tagged release, entries are labelled with their date and short commit hash (`main.__version__`
has been `1.0.0` since the initial commit).

## [Unreleased] — 2026-09-11

### Changed

- README quick start now uses the **`copy_launch.bat`** method instead of the hand-typed
  `sys.path.insert(...)` + `main.launch()` snippet: double-click the script in the project root,
  paste the copied command (it already carries this folder's absolute path) into Maya's Script
  Editor and press Enter. The command calls `main.reload_and_launch()`, which discards this
  project's cached modules first, so edits take effect without restarting Maya. The instructions
  now match [`INSTALL.md`](INSTALL.md) option A. Affects `README.md` and `README.zh.md`.
- Documented test count refreshed from the stale 136 to the actual **142** (12 widget tests are
  skipped in batch mode): README, INSTALL and LIMITATIONS (en + zh).
- `docs/USAGE.md` / `USAGE.zh.md`: expanded the Attribute Search reference — match-mode notes and a
  per-filter explanation (definition-level vs per-node validation, defaults, and the all-nodes rule
  for Locked / Connected).
- Chinese docs terminology: project-owned UI / feature names are now written in Chinese with the
  English label on first mention (README.zh, USAGE.zh, INSTALL.zh, ARCHITECTURE.zh,
  LIMITATIONS.zh); ASCII UI mock, program output and historical changelog entries are unchanged.
- `USAGE.md` / `USAGE.zh.md`: the match-mode table now uses examples that distinguish Contains from
  Prefix and states their nesting (Exact ⊆ Prefix ⊆ Contains).
- UI: the match-mode drop-down items carry tooltips explaining each mode.

### Added

- `LICENSE`: the project is released under the MIT License.
- `docs/CHANGELOG.md` and `docs/CHANGELOG.zh.md` to record notable changes.

### Fixed

- The **"Hide compound children"** search filter now actually works: `AttributeDefinition` gained
  `is_compound_child` (read via `MPlug.isChild`) and `SearchFilters.accepts_definition` drops child
  attributes such as `translateX` / `customVectorX` while keeping their parent, as
  `docs/USAGE.md` always described. Covered by two new tests (type resolution + search).

## [0b31bb0] — 2026-09-11

### Changed

- `bootstrap.ensure_on_path()` now always moves the project root to the **front** of `sys.path`
  (not only inserts it when missing), so names such as `core` / `ui` resolve to this project even
  when another flat-layout tool prepended its own root earlier.
- `bootstrap.release_conflicting_modules()` evicts foreign top-level modules **together with their
  cached submodules**: a stale `core.results` left behind by another tool used to shadow this
  project's imports after a take-over.
- Deferred `core` / `ui` imports moved to module top (kept: the `base` ↔ `channel_widgets` cycle
  and the intentional UI lazy-load in `main.py`).
- README / ARCHITECTURE / INSTALL (en + zh) document the two-way take-over contract ("last launched
  tool wins") and coexistence with `materialConvert`.

## [f8ea66b] — 2026-09-11

### Changed

- The "Keyable only" filter now keeps attributes that are keyable **or** shown in the Channel Box
  (Arnold reports `aiExposure` as `keyable=False`, `channelBox=True`, and such attributes can be
  keyframed from the Channel Box); the filter is checked by default and the tooltip / USAGE were
  updated accordingly.

### Added

- `AttributeDefinition.is_channel_box`, read via `MFnAttribute.channelBox`.
- Test coverage for the channelBox case (created through the OpenMaya API, because `addAttr` has no
  `channelBox` flag).

## [069e2ec] — 2026-09-11

### Added

- Initial release (`main.__version__` 1.0.0): batch attribute discovery & editing for Maya —
  recursive hierarchy traversal (incl. shapes), search by attribute name, real type resolution,
  compatibility validation (Locked / Connected / Missing / type mismatch), type-aware editors,
  preview + batch writing, and one Undo per Apply.
- `core` / `ui` / `utils` packages, the 136-test suite run under `mayapy`, `tools/selfcheck.py`,
  the one-click `copy_launch.bat` launcher, README and INSTALL / USAGE / ARCHITECTURE /
  LIMITATIONS docs (en + zh).
