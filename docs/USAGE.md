**English** | [中文](USAGE.zh.md)

# Usage

## 1. Interface overview

```
┌──────────────────────────────┬─────────────────────────┬─────────────────────┐
│ Scope · Search Range         │ Attribute Details       │ Technical Details   │
│ (•) Selection + all desc…    │ Name:       overrideCo… │ type=Color3         │
│ ( ) Selection only           │ Type:       Color3      │ api=kAttribute3Float│
│ [Refresh Selection]  17 nodes│ Matched:    38          │ unit=2 readOnly     │
│                              │ Writable:   35 / 38     │                     │
│                              │ Locked:     1           │                     │
│ Attribute Search             │ Connected:  2           │                     │
│ [ visibility______ ] [Cont▼] │ Missing:    3           │                     │
│ [ ]Writable only [ ]Keyable… │ Type mismatch: 0        │                     │
│ [ ]Hide locked [ ]Hide conn… │ Other-type nodes: none  │                     │
│                              │                         │                     │
│ Results                      │ Value                   │ Report · Log        │
│ Attribute | Type | Nodes |…  │ Color3, 38 nodes        │ ── intensity · 18 ──│
│ visibility (v) | Boolean |…  │ [✓] R [ 1.0 ]           │ [INFO] shape1: 1→18 │
│ overrideColorRGB | Color3 |… │ [✓] G [ 0.5 ]           │ [INFO] shape2: 1→18 │
│ translate (t) | Double3 |…   │ [✓] B [ 0.25]           │ [WARN] light1: none │
│                              │ [swatch] [Color Picker] │                     │
│                              │ [Load Current Value]    │                     │
│                              │                         │                     │
│                              │ Preview · Apply         │                     │
│                              │ Will modify 35, skip 3  │                     │
│                              │ [Preview]  [Apply]      │                     │
│                              │ Recorded as one Undo    │                     │
└──────────────────────────────┴─────────────────────────┴─────────────────────┘
```

---

## 2. Workflow

### Step 1: Choose the scope

Select one or more nodes in the viewport, then choose in **Scope**:

* **Selection + all descendants (incl. shapes)** (default) — when you select `Character_GRP`, it
  recursively includes every Transform, Shape and Intermediate Shape below it;
* **Selection only** — only the selected nodes themselves are processed.

> When a parent node and its child are both selected, the tool de-duplicates automatically: the
> child is not processed twice. The status bar reports
> “N de-duplicated (covered by other roots)”.

The tool **follows the Maya selection automatically**: picking new nodes rescans without any manual
step. The **Refresh Selection** button forces a cache-clearing rescan (for example after attributes
were changed by script).

### Step 2: Search for attributes

Type an attribute name into the search box. Matching is **case-insensitive** and matches both the
**long name and the short name**.

| Match mode | Behaviour | Example |
| --- | --- | --- |
| Contains (default) | the name contains the substring | `vis` → `visibility` |
| Exact | exactly equal | `visibility` matches, `vis` does not |
| Prefix | starts with the string | `trans` → `translate`, `translateX` |
| Fuzzy | subsequence match | `vsblt` → `visibility` |

Search results are **aggregated around the attribute** and sorted by the number of nodes involved,
from most to fewest:

```
visibility        Boolean   182 nodes
overrideColorRGB  Color3     38
transform         Double3    38
```

If the same attribute name is a **different type** on different nodes, those results are split into
**separate rows**, and the “same name, other type” column reports how many other nodes have a
different type. After you select one of those rows, only nodes with a compatible type are modified —
the tool never performs any implicit type conversion.

### Step 3: Confirm the details

Once you click a row, **Attribute Details** shows the real impact of this operation:

```
Name: color          Type: Color3
Matched: 58          Writable: 55
Locked: 2            Connected: 1        Missing: 14
```

* **Matched** — the number of nodes that have this attribute;
* **Writable** — of those, the number of nodes where the attribute is writable, not locked, has no
  incoming connection and is type-compatible;
* **Locked / Connected** — the nodes that will be skipped and why (they are never unlocked or
  disconnected automatically);
* **Missing** — the number of nodes in the scanned scope that do **not** have this attribute.

### Step 4: Set the value

The editor is generated automatically from the attribute's **real Maya type**:

| Type | Interface |
| --- | --- |
| Boolean | check box |
| Float / Double | numeric field (honours the range Maya declares) |
| Integer | integer field (a non-integer entry turns red and blocks Apply) |
| String | text field |
| Enum | drop-down (shows the enum names, writes the enum index to Maya) |
| Angle / Distance / Time | numeric field + unit hint (degrees / centimetres / frames) |
| Float3 / Double3 | three rows X / Y / Z, each with its own check box |
| Color3 | three rows R / G / B + colour swatch + **Color Picker…** |
| Compound | edit the child attributes one by one |
| Multi (array) | one row per existing element, e.g. `[0] value`, `[1] value` |

A few important points:

* **Every channel of a compound attribute has its own check box** — when you only want to change the
  G channel, just untick R/B and they will not be written as well;
* **Colours are not clamped**: if the underlying attribute allows values outside 0-1 (an HDR colour,
  for example), you can type `2.5` directly;
* The **Load Current Value** button reads the current value from the first usable node back into the
  editor (a read-only operation);
* When the input is invalid the field turns red, the **Apply** button is disabled, and the hint area
  explains why.

### Step 5: Preview

Click **Preview** (it does not modify the scene):

```
Will modify 175 nodes (175 channels), skip 7
Skip reasons: 5 Locked, 2 Connected
14 nodes with the same attribute name but a different type (excluded)
```

Below that, the **old → new value of every channel** plus the **skipped nodes and their
reasons** are listed, so you can check them one by one before anything is written.

### Step 6: Apply

Click **Apply** to execute. Every target is **re-validated** before it is written (does the node
still exist, is the attribute still valid, is it locked or connected, is the type still compatible),
so even if the scene has changed since the preview nothing is written incorrectly.

Result:

```
Succeeded:175  Skipped:7  Failed:0  (175 nodes touched)  Elapsed 12 ms
```

### Step 7: Undo

Press `Ctrl+Z` once and **the whole batch is reverted in one go** (not one undo per node).
This is implemented with Maya's Undo Chunk and has been verified by measurement on a 150-node batch
and in a partial-failure scenario.

---

## 3. Typical uses

### Turning visibility off in bulk

```
Select Character_GRP → search visibility → untick in Value → Preview → Apply → Ctrl+Z reverts the whole batch
```

### Changing colours in bulk

```
Search color → select overrideColorRGB (Color3)
→ pick a colour with Color Picker…, or type R/G/B directly
→ Preview → Apply
```

### Changing custom attributes in bulk

```
Search custom
→ customFloat      Float      12 nodes
   customBool       Boolean    12
   customString     String     12
   customColorRGB   Color3      8
Select one of the rows → the tool generates the matching editor for that row's type
```

### Changing only one component

```
Search translate → select translate (Double3)
→ untick X and Z, keep only Y → enter a value → Preview → Apply
```

### Changing array elements in bulk

```
Search input → select input
→ the editor lists [0] value / [1] value / [2] value (only **existing** elements are listed)
→ tick only the elements you want to change → Preview → Apply
```

---

## 4. Filters

| Filter | Effect | Cost |
| --- | --- | --- |
| Writable only | hides attributes Maya declares read-only | cheap |
| Keyable only | keeps only attributes that can be keyframed | cheap |
| User defined only | keeps only User Defined (dynamically added) attributes | cheap |
| Hide unsupported | hides types that cannot be edited such as matrix / message (on by default) | cheap |
| Hide compound children | hides children such as `translateX` and keeps only the parent attribute | cheap |
| Hide locked | hides attributes that are locked on every node | requires per-node validation, slower with many nodes |
| Hide connected | hides attributes that are connected on every node | requires per-node validation, slower with many nodes |

The first five can be decided while scanning attribute names and cost almost no time; the last two
need the plug state checked node by node, so they are off by default — turn them on when you need
them.

---

## 5. Operation audit (Report · Log)

The **Report · Log** panel audits every Apply and keeps the recent history (20 batches by default):

```
── intensity · 18 · 12:34:56 · 5 changed / 5 skipped ──
[INFO] |aiAreaLightShape1.intensity: 1 → 18
[INFO] |aiAreaLightShape2.intensity: 1 → 18
[WARNING] |aiAreaLight1.intensity: Attribute missing
```

* Successful writes use the normal colour, skips are yellow, failures are red, and the batch
  header is cyan;
* every line carries the **full write target** (node path + attribute/channel) and the
  **old → new value**;
* a failed entry automatically carries a `detail:` line with the exception type and the full
  plug name;
* **Clear** empties the history.

The tool **never swallows an exception silently**: a failed channel always appears here with a
reason.

---

## 6. Performance reference

Measured under Maya 2024.2 / mayapy (2100 descendant nodes, about 480,000 attributes):

| Stage | Time |
| --- | --- |
| DAG traversal | 0.003 s |
| First attribute scan (about 1500 nodes) | around 0.5 s |
| Later searches served from the cache | almost instant |
| 900 batch writes | 0.013 s |

The search box has a 260 ms debounce: while you keep typing it only scans once you pause. The tool
follows the Maya selection automatically (about 0.35 s debounce), so switching the selection needs no
manual refresh; the cache is discarded automatically when the scene is newly created / opened /
Undo / Redo happens and the tool rescans. The **Refresh Selection** button forces a cache-clearing
rescan.

---

## 7. Tips

* **Change only part of the nodes**: narrow the selection first (select only the target subtree),
  then use “Selection only”;
* **Confirm the impact**: review the old → new details and the skip reasons in the preview before applying;
* **Keep a way back**: every write this tool performs is an ordinary DG change and appears in the
  Undo queue, so one `Ctrl+Z` rolls the whole batch back;
* **Diagnosing same-name, different-type attributes**: when the “same name, other type” column of a
  result row is not empty, the scene contains attributes with the same name but a different type;
  they are excluded automatically (never implicitly converted).
