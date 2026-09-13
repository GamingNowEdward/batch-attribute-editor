**English** | [中文](ARCHITECTURE.zh.md)

# Batch Attribute Editor — Architecture

> Maya Batch Attribute Discovery & Editing System
>
> Target Maya version: **Maya 2024 (measured on 2024.2) / Python 3.10 / API 2.0**
> Every API conclusion in this document was verified by measurement on this machine with mayapy;
> the sources are in `tests/` and section 9.

---

## 1. Product goals

Inside the hierarchy of nodes the user has selected: recursively discover nodes, search attributes
by name, resolve the attribute's **real Maya type**, generate a matching editor for each type, safely
skip Locked / Connected / Missing / type-incompatible attributes, complete the batch edit with one
Apply, and make **the whole batch take only one Undo**.

The core is not `for node: cmds.setAttr(...)`, but:

```
Hierarchy Traversal → Attribute Discovery → Type Resolution
→ Compatibility Validation → Type-aware Editing → Batch Apply → Undo/Redo
```

---

## 2. Layering and data flow

The project uses a **flat layout**: `core` / `ui` / `utils` / `i18n` / `tests` sit directly in the
project root, so adding the project root to `sys.path` is enough to `import main`. Entry point and
bootstrap layer:

```
bootstrap.py    root-first sys.path handling + take-over of conflicting top-level modules (core / ui / utils / i18n…), incl. their cached submodules
main.py         launch() / close() / reload_and_launch(), window lifetime and scriptJob cleanup
__init__.py     optional facade: injects sys.path and then forwards to main (supports import BatchAttributeEditor)
```

> The price of the flat layout is that top-level names such as `core` / `ui` / `utils` / `i18n` are
> very common. `bootstrap` puts the project root first on `sys.path` and, by default, evicts every
> foreign module under a conflicting top-level name — the top-level package **and its cached
> submodules** (a stale `core.results` from another tool would otherwise shadow this project's
> imports). Conflicts are reported when they happen. The take-over is symmetric with other
> flat-layout tools (e.g. `materialConvert`): the last launched tool wins, while the already
> running tool keeps working from its imported module objects.

```
UI Layer (PySide6 / PySide2)
  main_window.py            orchestration: calls Core only, never manipulates Maya nodes directly
  panels.py                 Scope / Attribute Search / Results / Attribute Details / Value / Preview / Report sections
  attribute_model.py        search results → Qt table model
  editors/*                 editors generated on the fly from the attribute type (ValueEditorFactory)
  settings.py               language persistence (QSettings wrapper)
        │  (calls only Core's public API, no cmds.setAttr anywhere)
        ▼
Core Layer
  session.py        BatchAttributeSession facade: the UI's only entry point
  selection.py      SelectionManager      selection resolution, de-duplication, deciding the "unique roots"
  traversal.py      DAG traversal         recursively collects descendants (incl. Transform / Shape / Intermediate)
  attributes.py     AttributeScanner      enumerates node attributes, searches by name
  types.py          data model            AttributeKind / ChannelSpec / AttributeDefinition (pure data)
  type_resolver.py  TypeResolver          real attribute type resolution + channel construction (MObject / MPlug)
  compatibility.py  CompatibilityValidator existence / writability / lock / connection / type compatibility
  search.py         SearchEngine          aggregates results by (name, type) + statistics
  batch_setter.py   BatchSetter           preview and execution of batch writes
  undo.py           UndoManager           Undo Chunk management
  cache.py          ScanCache             scan cache and invalidation
  results.py        result dataclasses    Preview / ApplyReport (pure data)
        │
        ▼
Utils
  maya_utils.py     low-level helpers: node/plug name derivation, UUID re-checks, DAG tests
  logging_utils.py  two-channel logging (UI-friendly messages / technical details)
        │
        ▼
i18n (pure Python, no Qt / Maya dependency; imported by both Core and UI)
  manager.py        TranslationManager: catalog lookup, English fallback, {param} formatting, plural()
  en.py             English reference catalog (the exact historical English strings)
  zh_cn.py          Simplified Chinese catalog (key set identical to en.py, enforced by a test)
  __init__.py       public API: tr() / plural() / set_language() / get_language()
```

**One complete data flow:**

```
The user selects nodes
  → SelectionManager.resolve()        yields the Unique Root Set (de-duplicated)
  → DagTraversal.collect()            yields a NodeRecord list (incl. shapes)
  → AttributeScanner.scan()           yields attribute metadata for every node
  → SearchEngine.search(pattern)      yields an AggregatedAttribute list (grouped by type)
  → the user picks one entry
  → CompatibilityValidator.validate() yields a ValidateResult for every node
  → ValueEditorFactory.create()       builds the editor from the kind
  → BatchSetter.preview()             yields a PreviewReport (N will change / M skipped + reasons)
  → BatchSetter.apply()               writes inside one Undo Chunk and yields an ApplyReport
```

---

## 3. Node traversal strategy

* **Default scope**: the current selection + all of its DAG descendants (`MItDag` depth first). This
  is the UI mode `Selection + all descendants (incl. shapes)`; `Selection only` restricts the scan to
  the selected nodes themselves.
* They must be **DAG descendants**, so Transform, Shape and **Intermediate Shape** are all included.
* When a non-DAG node (such as a shader or a utility) is selected, only that node itself is scanned
  (it has no descendants). The traverser explicitly distinguishes `MFnDagNode` from
  `MFnDependencyNode` and does not fail just because there is no DAG path.
* The whole Dependency Graph is **not** traversed by default. DG search (connections / history /
  referenced nodes) is kept as an explicit extension point in `TraversalScope` inside `traversal.py`
  and is disabled by default.

**Measured evidence (probe 1):**

| Call | Result |
| --- | --- |
| `cmds.ls(node, shapes=True)` | **returns `[]`** — that form is not usable in this Maya version |
| `cmds.listRelatives(node, shapes=True)` | returns every shape (incl. intermediate) |
| `MItDag(kDepthFirst, kInvalid)` + `getPath()` | correctly yields depth / fullPathName / node type |

> The filter argument of `MItDag` **cannot** be used as a type filter on its own: with a `kMesh`
> filter the root transform is still returned. Type decisions are therefore always based on
> `path.node().hasFn(...)`, never on the iterator filter.

---

## 4. Attribute data model

Three levels with separated responsibilities:

| Class | Meaning | Lifetime |
| --- | --- | --- |
| `AttributeDefinition` | the attribute **definition** (type, constraints, units, enum fields, children) | produced by every scan, cacheable as pure data |
| `AttributeOccurrence` | one **occurrence of the attribute on a node** (node, plug name, locked/connected/exists) | produced by every validation |
| `AggregatedAttribute` | **one row** of a search result = a (name, kind) group + all occurrences + statistics | produced by every search |

**The same name with different types** is naturally modelled as different `AggregatedAttribute`
objects: the grouping key is `(name, kind)`, so `nodeA.someAttr(float)` and
`nodeB.someAttr(integer)` are two independent result rows; once the user picks one of them, only the
nodes compatible with that type are modified and the rest go into the skip report — no implicit type
conversion is performed anywhere.

`AttributeKind` values:
`FLOAT / DOUBLE / INT / BOOL / STRING / ENUM / ANGLE / DISTANCE / TIME /
VECTOR3 / COLOR3 / COMPOUND / MULTI / MATRIX / MESSAGE / UNKNOWN`

---

## 5. Type resolution (TypeResolver)

**Never guess the type from the value returned by `cmds.getAttr()`.** The decision is based on
`MObject` + `MFn*` metadata.

### 5.1 Measured API shapes (API 2.0, Maya 2024)

These details are extremely easy to get wrong; all of them were confirmed by measurement:

| Member | Shape | Notes |
| --- | --- | --- |
| `MFnAttribute.name` / `.shortName` | **attribute** | not a method |
| `MFnAttribute.dynamic` | **attribute** | use this to test for a "user defined attribute"; there is **no** `userDefined` |
| `MFnAttribute.keyable/.writable/.readable/.hidden/.connectable/.storable` | **attributes** | |
| `MFnAttribute.usedAsColor` | **attribute** | the key to the Color3 decision |
| `MFnNumericAttribute.numericType()` | **method** | |
| `MFnNumericAttribute.default` / `.usedAsColor` | **attributes** | |
| `MFnNumericAttribute.hasMin()/getMin()/hasMax()/getMax()` | **methods** | `getMin()` raises when there is no min, so `hasMin()` must be asked first |
| `MFnUnitAttribute.unitType()` | **method** | `kAngle=1 kDistance=2 kTime=3` |
| `MFnUnitAttribute.default` / `.hasMin()` / `.getMin()` | attribute / method / method | `getMin()` returns `MAngle`/`MDistance`/`MTime` |
| `MFnEnumAttribute.fieldName(i)` | **method**, takes an int | returns the field name |
| `MFnEnumAttribute.fieldValue(s)` | **method**, takes a **str** | passing an int raises TypeError |
| `MFnTypedAttribute.attrType()` | **method** | returns an `MFnData` type (`kString=4` etc.) |
| `MFnCompoundAttribute.numChildren()/child(i)` | **methods** | |
| `MFnMatrixAttribute.matrixType` | **does not exist** | a matrix can only be identified through `apiTypeStr` |
| `MPlug.isLocked/isConnected/isDestination/isSource/isCompound/isArray/isNull/isDynamic/isKeyable` | **attributes** | |
| `MPlug.numChildren()/numElements()/child(i)/elementByLogicalIndex(i)` | **methods** | calling `numChildren()` on a non-compound raises TypeError |
| `MPlug.isFreeToChange()` | **method** | `0=kFreeToChange 1=kNotFreeToChange 2=kChildrenNotFreeToChange` |
| `MPlug.isMulti` | **does not exist** | use `isArray` to test for an array |

### 5.2 Decision rules per type

| AttributeKind | Condition |
| --- | --- |
| `BOOL` | `kNumericAttribute` + `numericType()==kBoolean` |
| `FLOAT` / `DOUBLE` | `numericType()==kFloat` / `kDouble` |
| `INT` | `numericType()` ∈ {`kLong`,`kShort`,`kByte`,`kInt`,`kChar`} |
| `ENUM` | `attr.hasFn(kEnumAttribute)`; fields are enumerated with `fieldName(i)` |
| `STRING` | `kTypedAttribute` + `attrType()==kString` |
| `ANGLE`/`DISTANCE`/`TIME` | `attr.hasFn(kUnitAttribute)` + `unitType()` |
| `COLOR3` | `apiTypeStr ∈ {kAttribute3Float, kAttribute3Double}` **and** `MFnAttribute(attr).usedAsColor == True` |
| `VECTOR3` | as above but `usedAsColor == False` (for example `translate`, `apiTypeStr=kAttribute3Double`) |
| `COMPOUND` | `attr.hasFn(kCompoundAttribute)` and neither of the two kinds above |
| `MULTI` | `plug.isArray == True` (`is_multi` is flagged separately, outside the scalar types) |
| `MATRIX`/`MESSAGE` | decided by `apiTypeStr`; can only be recognised/inspected, no editor is provided |

**A genuine Color3, confirmed by measurement**: `transform.overrideColorRGB`,
`transform.objectColorRGB` and `lambert.color` are all `kAttribute3Float` + `usedAsColor=True` +
`plug.isCompound=True` + 3 child plugs.

**Child attributes are always accessed through the `plug.child(i)` index, never by concatenating
names**: in measurement the child attribute names of the very same `color` are `colorR/G/B`,
`overrideColorR/G/B` and `objectColorR/G/B` respectively — the names change from attribute to
attribute, the index is the stable structure. In addition, the children of `translate` —
`translateX/Y/Z` — are actually `kDoubleLinearAttribute` (unit attributes), which again can only be
discovered from metadata.

### 5.3 Testing whether an attribute exists (important)

Measured: **`findPlug("<attribute that does not exist>", False)` raises
`RuntimeError: (kInvalidParameter)`** and does not return a null plug; whereas `dep.attribute(name)`
does not raise and returns an `MObject` with `isNull()==True`.

Existence checks are therefore standardised as:

```python
attr = dep.attribute(name)          # does not raise
if attr.isNull():                   # MObject.isNull() is a method
    → the attribute does not exist
```

Attribute enumeration uses `dep.attributeCount()` + `dep.attribute(i)`; `findPlug(MObject, False)` is
safe when the attribute exists. `findPlug` is used only under these preconditions and never to probe
for existence.

---

## 6. Writing mechanism and Undo (the project's key decision)

### 6.1 Measured conclusions

| Write method | Does it enter the Undo queue? |
| --- | --- |
| `MPlug.setFloat/setInt/setBool/setString/...` | **No** (after 5 consecutive writes `undo()` fails immediately, pops=0) |
| `cmds.setAttr(...)` | **Yes** (5 writes = 5 undos, pops=5) |
| `cmds.setAttr` wrapped in `undoInfo(openChunk/closeChunk)` | **the whole block = 1 undo** (50 writes, pops=1) |
| a block containing failed writes | the successful part is still **one undo for the whole block** (pops=1) |

**Therefore: every write goes through `cmds.setAttr`, and the whole batch is wrapped in a single
Undo Chunk.**

### 6.2 Why this does not contradict "built on MPlug underneath"

The requirements ask that "string concatenation of `translateX/translateY/translateZ` must not be the
only data model" and that the bottom layer "prefer MPlug". This project honours the spirit of that by
splitting the work:

* **Discovery, type resolution, feasibility checks**: 100% based on `MObject` / `MPlug` structure
  (`plug.child(i)`, `plug.elementByLogicalIndex(i)`). What the data model stores is the **real
  structural information** derived from `MPlug`, not guessed names.
* **The target name used for writing** is exported by `MPlug` itself rather than concatenated:

  ```
  qualified = dagPath.fullPathName() + "." + plug.partialName(includeNodeName=False, useLongNames=True)
  ```

  Measurement shows that this gives authoritative and correct targets: `CubeA.w1`, `CubeA.warr[3]`
  (an array element), `CubeA.translateX` (a compound child) and `CubeAShape.visibility` (a shape),
  and that `cmds.setAttr` writes successfully to every one of these names.

The second reason for choosing `cmds.setAttr`: **the error messages are diagnosable**.
For a locked attribute the API setter only produces
`RuntimeError: (kFailure): Unexpected Internal Failure`, whereas `cmds.setAttr` produces
`setAttr: The attribute 'CubeA.lk' is locked or connected and cannot be modified.`
The latter can be presented to the user directly, which matches the requirement that "the UI shows
understandable information while the log keeps the technical details".

### 6.3 Undo Chunk management

* `UndoManager.chunk()` is a context manager: on entry `undoInfo(openChunk=True, chunkName=...)`, on
  exit `undoInfo(closeChunk=True)`.
* Measurement shows that `closeChunk` **succeeds silently** when no chunk is open (it does not
  raise), so the "loop over closeChunk until it raises" idiom is **never** used (that would hang
  Maya's main thread).
* Any single failed write inside the chunk is caught and recorded; it **does not abort the batch**
  and does not affect the undo integrity of that chunk.
* Known limitation: in a commandPort / no-full-event-loop context, the undo queue triggered from
  inside a Qt callback may be unreliable (the sibling project `attributeManager_maya` recorded the
  same phenomenon). Undo under real GUI interaction needs manual confirmation; the automated tests
  cover it down to the mayapy level.

---

## 7. Safety and compatibility policy

Non-destructive by default. **Never** performed automatically: unlock, disconnect, removing
connections, creating/deleting attributes, changing attribute definitions, deleting or renaming
nodes, and any implicit type conversion.

Decision order (`CompatibilityValidator`):

| Status | Basis | Default behaviour |
| --- | --- | --- |
| Missing | `dep.attribute(name).isNull()` | skip, counted as Missing |
| Not readable | `MFnAttribute.readable == False` | skip |
| Not writable | `MFnAttribute.writable == False` | skip |
| Locked | `plug.isLocked == True` | skip and report the reason (no automatic unlock) |
| Connected | `plug.isConnected` or `plug.numConnectedChildren() > 0` or `isFreeToChange()!=0` | skip and report the reason (no automatic disconnect) |
| Type mismatch | the `AttributeKind` of the attribute on that node ≠ the kind of the entry the user selected | skip, no implicit conversion |
| Multi element missing | `elementByLogicalIndex(i).isNull()` | skip (the first version does not create array elements) |

**Compound/multi caveat (measured)**: when only child plugs of a compound parent plug are connected,
`isConnected` on the parent is still `False`, while `isFreeToChange()` returns
`2 (kChildrenNotFreeToChange)`. The decision must therefore look at `isFreeToChange()` and the child
plugs together; looking only at the parent plug misses cases and causes failed writes.

---

## 8. Performance strategy

Measured (2100 descendant nodes, roughly 480,000 attribute entries):

| Stage | Time |
| --- | --- |
| `MItDag` collecting all DAG paths | 0.003 s |
| full attribute-name scan | 0.56 s |
| locating the target plug | 0.54 s |
| 900 chunked `cmds.setAttr` calls | 0.013 s |

Conclusion: **the bottleneck is attribute metadata scanning (about 0.27 ms/node); writing is
essentially free.**

Strategy:

1. `ScanCache` caches "attribute names per node → lightweight type summary" (pure Python data,
   **holding no MObject**).
2. **Correctness first**: the cache serves the search phase only; the Apply phase always
   **re-resolves** plugs and re-validates, so a stale cache can never cause a wrong write — the worst
   case is merely that search results look out of date.
3. Invalidation triggers: scene new/open/import, reference changes, Undo/Redo, node addition or
   removal, and the **node-count check** performed on a cache hit (`cmds.ls` counting is very cheap)
   — a mismatch invalidates the cache.
4. The UI **follows the Maya selection automatically** (`SelectionChanged` scriptJob + ~350 ms
   debounce). A selection-only change re-resolves and re-searches but **keeps the scan cache**, so
   following is nearly instant even on large scenes; unchanged selections and pure component
   selections are skipped without any scan. An explicit Refresh button forces a cache-clearing
   rescan (useful after attributes were changed by script).

MObject lifetime risk: an MObject becomes invalid once its node has been deleted. The cache therefore
**stores no MObject**, and Apply re-fetches `MFnDependencyNode` for every node.

---

## 9. Environment and compatibility record

| Item | Measured value |
| --- | --- |
| Maya | 2024 (`apiVersion 20240200`), 2024.2 environment |
| Python | 3.10.8 (mayapy) |
| Qt | 5.15.2 (mayapy site-packages contains **PySide2** only) |
| Target Qt | PySide6 preferred, PySide2 as fallback (GUI session); **the UI layer is not automatically tested under mayapy** |

Known environment anomalies (**they do not affect this tool, but they do affect the test fixtures**):

* Colour management fails to initialise on this machine (`OCIO profile Z:\ocio\...` is unreadable,
  `colorManagementPrefs -cmEnabled` is `False`).
* In that state `cmds.addAttr(attributeType="float3")` **fails silently** (the attribute is not
  created and nothing is raised); `attributeType="Float3"` explicitly reports
  "Type specified for new attribute is unknown". On the API side,
  `MFnNumericAttribute.createColor(name, kFloat)` also fails (TypeError).
* Color3 test data therefore always uses colour attributes that **really exist**
  (`transform.overrideColorRGB`, `lambert.color`) instead of creating them dynamically.
  The tool's recognition of, and writing to, both of them has been verified by measurement.

The localization layer keeps the same policy: the language switch is covered by automated tests
under mayapy, and the widget-level retranslation was additionally smoke-verified outside Maya with
**system Python 3.14 + PySide6 6.11 (offscreen platform, fake `maya` package)**: window construction,
English → 中文 → English switching (window title, buttons, table headers, details labels, editor unit
hints, colour-editor buttons). Under Maya 2024 the same code path runs on PySide2 5.15.2.

---

## 10. Relationship between UI and Core

* The UI contains **no** `cmds.setAttr` / `cmds.getAttr` / MPlug operations; it only calls Core's
  public API.
* Core does not import Qt and can be tested completely under mayapy.
* Dynamic editors are produced by `ValueEditorFactory` from the `AttributeKind`:
  `FloatEditor / IntEditor / BoolEditor / StringEditor / EnumEditor / VectorEditor /
  ColorEditor / UnitEditor`, all of which implement one uniform `ValueEditor` interface
  (`value()` / `set_value()` / `signal changed`), so adding a new type only requires registering one
  factory entry.

---

## 11. Extension points (reserved but disabled by default)

`TraversalScope` (DAG / connections / history / referenced), `AttributePreset` (save/load presets),
batch create/delete/copy/compare attributes, Namespace and NodeType filters, attribute search history.

Core's `SearchEngine` and `BatchSetter` both take "a set of nodes + an attribute definition" as input
and do not assume that the nodes came from a DAG traversal, so none of the extensions above requires
a change to the write layer.

---

## 12. Localization (UI language: English / 中文)

Design goals: **English is the default and the reference language**; the user can switch at any time
from the window; the text refreshes immediately without restarting Maya; the choice is persisted;
business logic and Maya data are untouched.

* **Layer boundary**: `i18n/` is a standalone pure-Python package, so `core` can use it without Qt
  or Maya, and `i18n` imports nothing from the project (no cycles). The UI reaches `QSettings` only
  through the `ui/qt.py` compatibility layer.
* **Key-based catalogs**: stable keys such as `window.title`, `status.locked`,
  `preview.describe.main`. The English and Chinese catalogs must contain exactly the same key set
  (enforced by a test). The English texts are **byte-identical to the historical literals**, so
  switching back to English reproduces the previous output exactly (the pre-existing English
  assertions in the test suite act as a regression net).
* **Fallback**: active language → English → the key itself. A malformed template or a missing
  `{param}` returns the raw text instead of raising — a missing translation can never crash the tool.
* **Placeholders**: dynamic values are `{named}` placeholders
  (`tr("results.empty_no_match", count=7)`), never f-strings scattered across widgets.
  `plural(count, "node")` renders `2 nodes` / `2 个节点` through the `counts.<noun>.<one|other>`
  entries and keeps the historical English pluralisation as the last resort for unknown nouns.
* **What is translated / not translated**: tool UI text (titles, buttons, tooltips, placeholders,
  statuses, reports, log messages at creation time) is translated. Maya data is never translated:
  node / attribute / plug names, enum field values, type labels (`Float`, `Double3`, …),
  `definition.describe()` metadata lines, exception text and tracebacks stay as they are.
* **Immediate refresh**: every panel exposes `retranslate()`; `BatchAttributeEditorWindow._retranslate()`
  updates the static texts, replays the dynamic state it owns (selection status, search summary and
  empty state, selected-attribute details, the currently shown Preview/Apply report, the validation
  error, the value hint) and calls `retranslate()` on the **existing** editors. Widgets are not
  recreated and user input is not lost.
* **Audit log**: log entries and batch headers keep the language they were written in — they are a
  record of past operations; entries created after a switch use the new language. The empty state
  and the panel frame follow the active language.
* **Persistence**: `ui/settings.py` uses
  `QSettings("BatchAttributeEditor", "BatchAttributeEditor")`, key `language`, native format
  (the Windows registry on this platform) - no extra configuration file and no hard-coded path.
  First launch (nothing stored), a blank value or a failing store all fall back to English.
  `main.launch()` restores the persisted language **before** the window builds its texts.
* **Switch UI**: a `Language:` selector in the top-right corner of the window (`English` / `中文`).
  Switching calls `set_language()`, saves the choice and runs the retranslation pass; unknown or
  foreign spellings (`zh`, `zh-cn`, `en_US`, …) are normalised, and unknown languages fall back to
  English.
* **Bootstrap**: `bootstrap.TOP_LEVEL_MODULES` includes `i18n`, so `reload_and_launch()` and the
  same-name module take-over treat it like the other top-level packages.

Coverage: `tests/test_i18n.py` (manager switching / fallback / formatting / plural, catalog key and
placeholder parity, source scan for literal `tr("...")` keys, QSettings persistence with fake and
real backends, Core report texts, GUI language switching) plus the existing English assertions.
