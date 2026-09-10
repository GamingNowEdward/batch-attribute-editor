**English** | [中文](INSTALL.zh.md)

# Installation

## 1. Requirements

| Item | Requirement | Notes |
| --- | --- | --- |
| Maya | **2024 / 2024.2** (the versions actually tested) | Uses Maya API 2.0; 2022–2023 are expected to work but were not tested |
| Python | 3.10 (bundled with Maya) | No third-party libraries needed |
| Qt | PySide2 5.15 or PySide6 | Both are supported and auto-detected; the mayapy bundled with Maya 2024.2 only ships PySide2 |
| Operating system | Windows / macOS / Linux | Only tested on Windows + Maya 2024.2 |

**There are no pip dependencies at all.** The tool only uses the `maya.cmds` and
`maya.api.OpenMaya` modules and PySide that ship with Maya.

---

## 2. Installation

The tool is a pure Python package, so installing it just means making it `import`-able from Maya.
Pick any one of the options below.

### Option A: One-click command copy (fastest — nothing to configure)

Double-click **`copy_launch.bat`** in the project root. It puts this command on your clipboard,
with the project's absolute path already filled in:

```python
import sys; sys.path.insert(0, r"C:\opencode\BatchAttributeEditor"); import main; main.reload_and_launch()
```

Paste it into Maya's **Script Editor** (Python tab) and press Enter.

* The script does **not** start Maya — it only fills the clipboard, so you keep using the session
  you already have open.
* It uses `reload_and_launch()` rather than `launch()`: Python caches imported modules, so after you
  edit a file here a plain `import main` keeps handing back the **old** code until Maya is
  restarted. That is the usual reason a change appears to have no effect — for example a window
  that still shows a title from an earlier version. Reloading discards the cached copy first.
* The path is resolved when the script runs, so the project can live on a USB stick, a network
  share, any drive letter or a renamed folder, and the pasted command still works.
* The console window also prints two other useful commands (self-check and the test suite) for
  copying by hand.

### Option B: Temporary load from the Script Editor

```python
import sys
sys.path.insert(0, r"C:\opencode\BatchAttributeEditor")
import main
main.launch()
```

Same as Option A, typed by hand. Good for trying it out first — you need to run it again after
restarting Maya. (`copy_launch.bat` exists precisely so you do not have to type or edit the path.)

### Option C: Shelf button (recommended for daily use)

1. In Maya open the **Script Editor**, switch to the **Python** tab, paste the three lines from
   Option B and run them once (to confirm they work);
2. Select all three lines and **middle-mouse drag them onto the shelf** — a button is created
   automatically;
3. From then on, one click on that button opens the window.

### Option D: Put it in Maya's scripts directory (available as Maya starts up)

The project has a **flat layout** (`main.py` / `core/` / `ui/` sit directly in the project root), so
put the **whole project folder** into the scripts directory — but keep the extra folder level; do
not spread its contents directly into `scripts\`, otherwise generic names such as `core` / `ui` /
`utils` would pollute Maya's top-level namespace.

```
C:\Users\<username>\Documents\maya\2024\scripts\BatchAttributeEditor\
    main.py
    core\
    ui\
    ...
```

Then there are two ways to use it:

```python
import sys
sys.path.insert(0, r"C:\Users\<username>\Documents\maya\2024\scripts\BatchAttributeEditor")
import main
main.launch()
```

Or combine it with Option E to have it load automatically with Maya.

### Option E: Open automatically with Maya

Add the following to `Documents\maya\2024\scripts\userSetup.py` (create the file if it does not
exist):

```python
import sys

_BAE_PATH = r"C:\opencode\BatchAttributeEditor"   # replace with your actual path
if _BAE_PATH not in sys.path:
    sys.path.insert(0, _BAE_PATH)


def _open_batch_attribute_editor():
    try:
        import main
        main.launch()
    except Exception as exc:
        print(f"[Batch Attribute Editor] Auto-open failed: {exc}")


import maya.utils
maya.utils.executeDeferred(_open_batch_attribute_editor)
```

> Note: the code in `userSetup.py` runs while Maya is starting up. The snippet above defers opening
> the window until Maya has fully initialised (`executeDeferred`) and wraps it in `try/except` so
> that Maya's start-up is not affected.

---

## 3. Verifying the installation

### 3.1 Quick verification (no nodes need to be created)

Run this in the Script Editor:

```python
import sys
sys.path.insert(0, r"C:\opencode\BatchAttributeEditor")
import main
print("version", main.__version__)
main.launch()
```

Once the window appears:

1. Select any node with a hierarchy in the viewport (a group, for example);
2. Set **Scope** to “Selection + all descendants (incl. shapes)”;
3. The tool follows the Maya selection automatically; the status bar should show the number of nodes
   scanned, for example `17 nodes (1 root) · 17 nodes, Transform 11, Shape 6`;
4. Type `visibility` into the search box; `visibility | Boolean | <node count>` should appear in
   Results.

### 3.2 Full self-check (creates temporary nodes and deletes them afterwards)

```python
import sys
sys.path.insert(0, r"C:\opencode\BatchAttributeEditor")
import tools.selfcheck
tools.selfcheck.run(create_test_nodes=True)
```

The self-check verifies, in order: module imports, main window construction, DAG traversal
(incl. shapes), attribute search, type resolution, preview, batch writing, and
**“a whole batch costs exactly one Undo”**, then deletes the temporary nodes.
Output that ends with `All checks passed` means everything is fine.

### 3.3 For developers: running the automated tests

Run this from the project root:

```powershell
& "C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe" tests\run_tests.py
```

The expected output is `Ran 142 tests ... OK` (of which the 12 widget tests that need a GUI are
skipped in batch mode).

These tests do **not** affect the Maya session you are working in: `mayapy` is a separate process
using its own temporary scene.

---

## 4. Uninstalling

* Option A / B / C: delete the shelf button, or simply stop running those few lines;
* Option D / E: delete the `scripts\BatchAttributeEditor` folder and remove the snippet you added to
  `userSetup.py`;
* The tool writes **no** data into the scene (it creates no nodes, writes no attributes and adds no
  scriptNode), so nothing is left behind in scene files you have already opened.

---

## 5. FAQ

**Q: `import main` raises `ModuleNotFoundError`?**
What you insert into `sys.path` should be the **project root itself** (the folder in which
`main.py`, `core\` and `ui\` are visible), not its parent directory — with a flat layout the
modules live in the root.

**Q: `import main` picks up something else / `import core` raises a strange error?**
With a flat layout `core` / `ui` / `utils` / `tests` are very common names and may already be taken
by another plug-in using the same layout (e.g. `materialConvert`). `main.launch()` handles this
automatically: it puts this project first on `sys.path` and evicts the foreign top-level modules
**together with their cached submodules** (printing a notice when it does so), so both tools can
coexist in one Maya session ("last launched tool wins"). If the problem persists, check whether
some plug-in's module name collides with this project.

**Q: The window opens empty / says “no nodes scanned yet”?**
Select at least one node in the viewport — the tool scans it automatically (or click
**Refresh Selection** to force a cache-clearing rescan).
Also note that `cmds.ls(selection=True)` returns Transforms only; shapes are picked up
automatically by the tool as descendants.

**Q: Clicking Apply does nothing?**
You must click **Preview** first. Any change to a value invalidates the preview and disables
**Apply** — this is an intentional safety design: it makes sure you only write to the scene after
you have seen “N will be modified / M skipped”.

**Q: Can I dock it into the right-hand panel?**
The window opens floating by default; just drag it into one of Maya's docking areas. You can also
dock it to the right directly from code with `main.launch(dock=True)`.
