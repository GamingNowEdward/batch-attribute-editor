[English](INSTALL.md) | **中文**

# 安装说明

## 1. 环境要求

| 项目 | 要求 | 说明 |
| --- | --- | --- |
| Maya | **2024 / 2024.2**（实测版本） | 使用 Maya API 2.0；2022–2023 预期可用但未实测 |
| Python | 3.10（Maya 自带） | 不依赖任何第三方库 |
| Qt | PySide2 5.15 或 PySide6 | 两个都支持，自动探测；Maya 2024.2 自带的 mayapy 只有 PySide2 |
| 操作系统 | Windows / macOS / Linux | 仅在 Windows + Maya 2024.2 上实测 |

**没有任何 pip 依赖**。工具只使用 Maya 自带的 `maya.cmds`、`maya.api.OpenMaya` 与 PySide。

---

## 2. 安装

工具是一个纯 Python 包，安装 = 让 Maya 能 `import` 到它。任选一种方式。

### 方式 A：一键复制命令（最快，无需任何配置）

双击项目根目录下的 **`copy_launch.bat`**，它会把下面这条命令放进剪贴板，
其中的路径已经是当前项目所在位置的绝对路径：

```python
import sys; sys.path.insert(0, r"C:\opencode\BatchAttributeEditor"); import main; main.reload_and_launch()
```

粘贴到 Maya 的 **Script Editor**（Python 标签）里回车即可。

* 该脚本**不会**启动 Maya，只是填好剪贴板，你继续用已经开着的 Maya；
* 用 `reload_and_launch()` 而不是 `launch()`：Python 会缓存已导入的模块，改完文件后直接
  `import main` 拿到的仍是**旧代码**，除非重启 Maya —— 这正是"改了没生效"（例如窗口标题
  还是上一版）的常见原因。这个命令会先丢弃缓存再重新导入；
* 路径在运行时解析，所以项目放在 U 盘、网络盘、任意盘符或改名后的文件夹里都能直接用，
  粘出来的命令不需要手改；
* 命令行窗口里还会打印另外两条常用命令（自检、自动化测试）供手动复制。

### 方式 B：Script Editor 临时加载

```python
import sys
sys.path.insert(0, r"C:\opencode\BatchAttributeEditor")
import main
main.launch()
```

和方式 A 相同，只是手输。适合先试用，Maya 重启后需要重新执行。
（`copy_launch.bat` 的存在就是为了让你不必手输、也不必手改路径。）

### 方式 C：工具架按钮（推荐日常使用）

1. 在 Maya 里打开 **Script Editor**，切到 **Python** 标签，粘贴方式 B 的三行并执行一次（确认能用）；
2. 全选这三行，用鼠标**中键拖到工具架**上，自动生成一个按钮；
3. 以后点一下按钮即可打开。

### 方式 D：放进 Maya 脚本目录（随 Maya 启动可用）

项目是**扁平结构**（`main.py` / `core/` / `ui/` 直接位于项目根），所以把**整个项目文件夹**
放到脚本目录下即可 —— 注意保留一层文件夹，不要把里面的内容直接铺进 `scripts\`，
否则 `core` / `ui` / `utils` 这些通用名字会污染 Maya 的顶层命名空间。

```
C:\Users\<用户名>\Documents\maya\2024\scripts\BatchAttributeEditor\
    main.py
    core\
    ui\
    ...
```

然后有两种用法：

```python
import sys
sys.path.insert(0, r"C:\Users\<用户名>\Documents\maya\2024\scripts\BatchAttributeEditor")
import main
main.launch()
```

或者配合方式 E 让它随 Maya 自动加载。

### 方式 E：随 Maya 自动打开

在 `Documents\maya\2024\scripts\userSetup.py` 里加入（文件不存在就新建）：

```python
import sys

_BAE_PATH = r"C:\opencode\BatchAttributeEditor"   # 换成你的实际路径
if _BAE_PATH not in sys.path:
    sys.path.insert(0, _BAE_PATH)


def _open_batch_attribute_editor():
    try:
        import main
        main.launch()
    except Exception as exc:
        print(f"[Batch Attribute Editor] 自动打开失败：{exc}")


import maya.utils
maya.utils.executeDeferred(_open_batch_attribute_editor)
```

> 注意：`userSetup.py` 里的代码会在 Maya 启动时运行。上面的写法把打开窗口延后到 Maya
> 完全初始化之后（`executeDeferred`），并且用 `try/except` 包住，避免影响 Maya 启动。

---

## 3. 验证安装

### 3.1 快速验证（不需要创建任何节点）

在 Script Editor 里执行：

```python
import sys
sys.path.insert(0, r"C:\opencode\BatchAttributeEditor")
import main
print("版本", main.__version__)
main.launch()
```

窗口出现后：

1. 在视口里选中任意一个带层级的节点（例如一个 group）；
2. **范围（Scope）** 选择「当前选择 + 所有后代（含 Shape）」；
3. 工具会自动扫描当前选择，状态栏应显示扫描到的节点数，例如
   `17 nodes, 11 transforms, 6 shapes · 1 root node`；
4. 在搜索框输入 `visibility`，**结果（Results）**里应出现 `visibility | Boolean | <节点数>`；
5. （可选）把右上角的 `语言：` 选择器切到中文 —— 整个窗口应立即更新，切回 English 应立即恢复。

### 3.2 完整自检（会建临时节点，用完即删）

```python
import sys
sys.path.insert(0, r"C:\opencode\BatchAttributeEditor")
import tools.selfcheck
tools.selfcheck.run(create_test_nodes=True)
```

自检会依次验证：模块导入、主窗口构建、DAG 遍历（含 Shape）、属性搜索、类型识别、
预览、批量写入，以及**"整批写入只占一次撤销"**，最后删除临时节点。
输出以 `All checks passed` 结尾即为正常。

### 3.3 开发者：运行自动化测试

在项目根目录下运行：

```powershell
& "C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe" tests\run_tests.py
```

预期输出 `Ran 171 tests ... OK`（其中 13 个需要 GUI 的 widget 测试在 batch 模式下跳过）。

这些测试**不会**影响你正在使用的 Maya 会话：`mayapy` 是独立进程，使用自己的临时场景。

---

## 4. 卸载

* 方式 A / B / C：删除工具架按钮，或不再执行那几行代码即可；
* 方式 D / E：删除 `scripts\BatchAttributeEditor` 文件夹，并移除 `userSetup.py` 里加入的片段；
* 工具**不会**向场景写入任何数据（不创建节点、不写属性、不加 scriptNode），
  因此已经打开的场景文件里不会残留任何东西；
* 场景之外唯一的持久化痕迹是界面语言偏好，由 `QSettings` 记录在注册表
  `HKEY_CURRENT_USER\Software\BatchAttributeEditor\BatchAttributeEditor`（值 `language`）；
  需要彻底清理时删除该注册表键即可。缺失或非法值只会回退到 English，保留也无副作用。

---

## 5. 常见问题

**Q：`import main` 报 `ModuleNotFoundError`？**
`sys.path` 里加的应当是**项目根目录本身**（那里面能看到 `main.py`、`core\`、`ui\`），
而不是它的上一级目录 —— 扁平结构下模块就在根目录里。

**Q：`import main` 拿到的却是别的东西 / `import core` 报奇怪的错？**
扁平结构下 `core` / `ui` / `utils` / `tests` 是很常见的名字，可能被其它同样采用扁平结构的
插件占用（例如 `materialConvert`）。`main.launch()` 会自动处理：把本项目置顶到 `sys.path`，
并把同名顶层模块**连同其缓存的子模块**一起释放（同时打印提示），因此两个工具可以在同一个
Maya 会话中共存（"后启动者赢"）。如果问题依旧，检查是否有插件的模块名与本项目撞车。

**Q：窗口打开后是空的 / 显示"尚未扫描到节点"？**
先在视口里选中至少一个节点，工具会自动扫描（也可以点 **刷新选择** 强制清缓存重扫）。
另外注意 `cmds.ls(selection=True)` 只返回 Transform，Shape 由工具作为后代自动纳入。

**Q：点「应用」没反应？**
必须先点 **预览**。任何数值改动都会让预览失效并禁用「应用」，这是有意的安全设计：
确保你在看清"将修改 N 个 / 跳过 M 个"之后才写入场景。

**Q：想停靠到右侧面板？**
窗口默认浮动打开，直接拖到 Maya 的停靠区域即可；
也可以在代码里用 `main.launch(dock=True)` 直接停靠到右侧。

**Q：怎么把界面切换成中文（或切回英文）？**
用窗口右上角的 `语言：` 选择器即可，立即生效、不需要重启 Maya。选择会被记住，下次打开工具
自动恢复（首次启动默认 English）。如果想手动重置，删除注册表键
`HKEY_CURRENT_USER\Software\BatchAttributeEditor\BatchAttributeEditor` 后会回退到 English。
