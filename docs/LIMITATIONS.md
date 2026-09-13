**English** | [中文](LIMITATIONS.zh.md)

# Known Limitations

This file records the things the **current version genuinely cannot do, or where a trade-off was
made**, together with the measurements behind them. Every entry tries to give both the “why” and the
“how to work around it”.

---

## 1. Verification coverage

| Part | Status |
| --- | --- |
| Core (traversal / type resolution / validation / search / writing / Undo) | ✅ 158 automated tests pass under mayapy on Maya 2024.2 (16 GUI tests skipped; 174 total) |
| Undo granularity (one Apply = one Undo) | ✅ verified by measurement (150-node batch, partial-failure scenario) |
| UI module imports and factory dispatch | ✅ verified automatically |
| Localization (language switch / fallback / persistence / Core texts) | ✅ automated under mayapy; the widget-level retranslation was additionally smoke-verified with PySide6 6.11 (offscreen, fake `maya`) |
| **UI window construction and display** | ✅ confirmed in a real Maya 2024.2 GUI (PySide2 5.15.2) |
| **UI interaction details** | ⚠️ **not automatically verified** (button clicks, colour picker and docking drags need hands-on testing) |

**Measured record of the window build** (output of `tools/selfcheck.py` in a real Maya GUI session):

```
[ok]   Main window constructed
Window shown
[ok]   Traversal: 9 nodes, 4 of them shapes
[ok]   Search: baeWeight · Float · 4 nodes
[ok]   Preview: Will modify 4 nodes (4 channels), skip 5
[ok]   Apply: Succeeded:4  Failed:0  (4 nodes touched)  Elapsed 1 ms
[ok]   Write check: baeWeight = 0.41999988697815
[ok]   Undo: the batch of 4 writes took 1 Undo
===== Batch Attribute Editor self-check result =====
All checks passed
```

(`skip 5` is because the root node itself has no `baeWeight` attribute; this is a correct
missing-node count.)

**Why widget-level tests cannot be automated**: under `mayapy` / `standalone` a `QApplication`
cannot be created — in testing, as soon as one was attempted the process exited immediately with
`QWidget: Cannot create a QApplication`. Therefore the 16 widget tests in `test_ui_smoke.py` /
`test_i18n.py` that need a QWidget are skipped automatically in batch mode, and the window and its
interactions can only be confirmed in a real GUI session. (The language-switch retranslation pass
was additionally exercised outside Maya with a real Qt application — system Python + PySide6 +
offscreen platform, `maya` package faked — as a cross-binding smoke check.)

**Interactions not yet confirmed item by item**: the colour picker button, ticking only some
channels, ticking the filters, and layout persistence after docking to a panel. If a problem shows
up, the Script Editor output and the contents of the **Report · Log** panel can be used directly to
track it down.

### Docking behaviour

The window is implemented with `MayaQWidgetDockableMixin` + a plain `QWidget` (**deliberately not a
`QMainWindow`**: a window carrying the `Qt.Window` flag recreates its native handle when Maya folds
it into a tab, which carries a crash risk). It opens as a floating window by default; you can drag
it into a docking area by hand, or use `launch(dock=True)` to dock it straight to the right.

Persistence of the workspace layout (whether the window position is restored after restarting Maya)
is **not handled specifically** and is outside the verified scope.

---

## 2. Multi / array attributes

* **Only array elements that already exist are edited** — no new elements are created, no elements
  are deleted, and the array is never extended automatically;
* The set of array indices of one attribute can differ between nodes (`input[0]` exists on only some
  nodes). The editor lists all channels as the **union**; every node is re-validated at write time,
  and an element that does not exist on a node is counted as “Array element missing” and skipped;
* Structural operations such as `setNumElements` are out of scope.

**Why**: the requirements explicitly asked the first version to edit existing elements only;
creating/deleting elements is a structural change and carries higher risk (it alters topology and
history), so it needs a separately designed confirmation flow.

---

## 3. Types that cannot be edited

| Type | Status |
| --- | --- |
| Matrix | recognised and displayed only; no editor |
| Message | recognised and displayed only (it is a placeholder attribute used for connections and has no writable value) |
| 2-component numeric compounds (k2Float / k2Double) | classed as Compound and edited child by child |
| Generic / plug-in custom data types | recognised as Unknown; no editor |

These attributes do appear in the search results (unless “Hide unsupported” is ticked), but once
selected, the Value area states that the type is not editable yet (recognition and inspection only),
instead of offering a control that would write the wrong thing.

---

## 4. Deliberate safety trade-offs

The following operations are **never performed automatically**, and the current version provides
**no** switch to enable them:

* unlocking an attribute (`lock=False`)
* breaking an existing connection (`disconnectAttr`)
* creating / deleting attributes or array elements
* implicit type conversion (writing a float as an int, a String as a number, and so on)
* deleting or renaming nodes

Locked or connected targets are skipped with a reason. If you really need to change such an
attribute, unlock / disconnect it by hand first (this friction is intentional: destructive
operations must be started explicitly by a human).

---

## 5. Limits of the search scope

* By default only **DAG descendants** are recursed (Transform, Shape, Intermediate Shape).
* The whole Dependency Graph is **not** recursed. Reason: the DG can be enormous, and it would drag
  in nodes that do not belong to the current hierarchy (history, utility and shader networks).
* When a non-DAG node is selected (a lambert material, for example), only that node itself is
  scanned — this is correct behaviour, but it means that “select a shader and batch-change its
  colour” requires selecting all the relevant nodes.
* The code reserves extension slots in `TraversalScope` such as `DEPENDENCY_CONNECTIONS` /
  `HISTORY` / `REFERENCED`, but they are **not implemented**, and the default never quietly enables
  them.

---

## 6. Handling of unit attributes

* Angle / Distance / Time are displayed and entered in **Maya's current working units** (by default:
  degrees / centimetres / frames), consistent with the units of `cmds.getAttr` / `cmds.setAttr`;
* If you change the working units to inches or radians, the numbers in the interface change with
  them (that is Maya's semantics);
* The hard range of a unit attribute is converted to degrees / centimetres / frames before display;
  it is a hint only and is **not used for clamping**.

---

## 7. Cache

* The scan cache is used during the search stage only; **Apply always resolves the plug again and
  re-validates**, so even if the cache is stale the worst case is a stale search result — **it never
  writes to the wrong node**.
* Invalidation points: an explicit refresh, a new/opened scene, Undo/Redo.
* Following the selection re-resolves the selection but **keeps the cache** (a selection change does
  not affect attribute tables), which is what makes switching selections fast.
* Known gap: adding or removing attributes directly from a script with `addAttr` / `deleteAttr` does
  **not** trigger cache invalidation (Maya has no lightweight “attribute table changed”
  notification). Clicking **Refresh Selection** once is enough in that case.

---

## 8. Known environment-related issues (measured on this machine)

These are problems of the **runtime environment**, not defects of the tool, but they affect how test
fixtures are built:

| Symptom | Measured result | Impact |
| --- | --- | --- |
| Colour management fails to initialise | `OCIO profile Z:\ocio\...` cannot be read, `colorManagementPrefs -cmEnabled` is `False` | none (the tool does not depend on colour management) |
| `cmds.addAttr(attributeType="float3")` | **fails silently**: it raises no exception, but the attribute is not created | Color3 test attributes cannot be created from a script; the tests use colour attributes that really exist instead (`overrideColorRGB`, `lambert.color`) |
| `cmds.addAttr(attributeType="Float3")` | reports `Type specified for new attribute is unknown` outright | same as above |
| `MFnNumericAttribute.createColor(name, kFloat)` | `TypeError: argument 2 must be str, not int` | same as above |

> If you need to create a Color3 attribute in a scene, use the Attribute Editor's
> `Add Attribute → Color` or the normal `addAttr -at float3` flow;
> the tool's own **recognition and writing** of Color3 has already been verified on real colour
> attributes.

Other measured Maya API traps (already worked around in the code, recorded for reference):

* After a node is deleted, an old `MObject` still reports `isNull() == False`, and
  `name()` / `attributeCount()` / `findPlug()` keep returning **stale data without raising an
  error** — which is why every re-check relocates the node by **UUID**;
* `MFnDependencyNode.uuid()` returns an `MUuid` **object** rather than a `str` under API 2.0, and it
  must be converted to a string before it can be handed to `cmds.ls`;
* `MPlug.isConnected` is `True` for the connection **source** as well; only `isDestination` means
  the write is ineffective;
* a compound parent plug still reports `isConnected` as `False` when only a child plug is connected
  (you need `numConnectedChildren()` / `isFreeToChange()` to detect it);
* an `MPlug` setter write (`setFloat` / `setInt` / `setBool` / `setString` / …) does **not enter the
  Undo queue** (measured: after 5 consecutive writes `undo()` fails outright, pops=0), whereas
  `cmds.setAttr` does enter it (5 writes = 5 undos), so all writes go through `cmds.setAttr` — and
  `cmds.setAttr` inside an Undo chunk is exactly 1 Undo for the whole batch;
* `cmds.ls(node, shapes=True)` returns an empty list in this version, so traversal must use `MItDag`;
* `undoInfo(query=True, length=True)` returns the queue **capacity**, not the number of entries.

---

## 9. Version compatibility

* Development and testing were both done on **Maya 2024 / 2024.2 + Python 3.10 + Maya API 2.0**.
* Maya 2022 / 2023 are **expected to work but were not tested**: the code depends only on API 2.0
  and long-stable `cmds`; the 2.0 API has been available since Maya 2016.
* Maya 2025 / 2026 have **not been tested**. The main risk points are the Qt version (PySide6 is
  already supported) and differences in the behaviour of `mayaMixin`.
* If you run into problems on another version, `tools/selfcheck.py` prints the exact module and
  exception, which makes them easier to locate.

---

## 10. Not implemented yet (listed as “future extensions” in the requirements)

The following capabilities have a reserved place in the architecture, but are **not implemented in
the current version**:

* batch creating / deleting / copying / comparing attributes
* batch saving and loading of attribute presets (Attribute Presets)
* attribute search history
* Dependency Graph search, namespace filtering, node type filtering
* destructive advanced options such as forced writes after disconnecting and forced unlocking
* creating and deleting array elements
* background-thread scanning (search is currently synchronous; a very large scene briefly blocks the
  interface, which shows a wait cursor in the meantime)

---

## 11. Localization (UI language)

* Only **English and Simplified Chinese** are shipped. Adding a language means adding a catalog whose
  key set matches the English reference exactly (registered in `i18n/manager.py`) plus one selector
  entry; no UI code needs to change.
* **Audit-log entries keep the language they were written in** — they are a record of past
  operations. Entries created after a switch use the new language; the currently displayed
  Preview / Apply report, the status lines and the details refresh immediately.
* **Input-validation errors that already contain data** (for example `channel: <coercion error>`)
  are shown as they were rendered; changing the input again renders them in the new language.
* **Type labels stay English by design**: `Float`, `Double3`, `Compound`, `Matrix`, … are treated
  like Maya type names and are never translated; the same applies to the `type=/api=/numeric=`
  metadata lines in Technical Details.
* The language preference is **global per user**, not per scene or per Maya version (stored through
  `QSettings`), and is restored on the next `launch()`.
* Switching languages refreshes the open window in place — no widget is recreated, so the current
  table selection, editor input and log history survive. If a third party calls
  `i18n.set_language()` directly, the open window is not notified automatically; use the in-window
  selector instead.
