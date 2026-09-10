[English](README.md) | **中文**

# Batch Attribute Editor · Maya 批量属性编辑器

> 一个用于 Maya 的**批量属性发现与编辑系统**：在选中的层级里递归找到节点（含 Shape），
> 按属性名搜索、识别真实 Maya 类型、为不同类型生成对应编辑器、安全跳过
> 锁定（Locked）/ 已连接（Connected）/ 缺失（Missing）/ 类型不兼容的属性，一次应用（Apply）完成批量修改，
> 并且整批修改**只占一次撤销（Undo）**。

目标环境：**Maya 2024 / 2024.2**（Python 3.10、Maya API 2.0、PySide2 5.15.2 或 PySide6）。
本文档中的所有 API 行为都经过本机 mayapy 实测，依据见 [`docs/ARCHITECTURE.zh.md`](docs/ARCHITECTURE.zh.md)。

<p align="center">
  <img src="docs/images/ui.webp" alt="Batch Attribute Editor 界面" width="960">
</p>
<p align="center"><em>Batch Attribute Editor：左侧为范围 / 搜索 / 结果，中间为属性详情 /
值编辑 / 预览应用，右侧为技术详情与操作审计日志。</em></p>

---

## 它能解决什么

Maya 原生 Attribute Editor 只针对当前单个节点，Channel Box 能显示的属性有限，
也无法"按属性名在整个层级里搜索并批量修改"。本工具补上这一段：

```
选择节点 → 递归遍历（含 Shape / Intermediate Shape）→ 按属性名搜索
→ 识别真实类型 → 生成类型对应的编辑器 → 预览将修改/将跳过 → 批量写入 → 一次撤销
```

它不是 `for node in nodes: cmds.setAttr(...)`，核心能力是：

```
Hierarchy Traversal + Attribute Discovery + Type Resolution
+ Compatibility Validation + Type-aware Editing + Batch Apply + Undo/Redo
```

---

## 快速开始

双击项目根目录下的 **`copy_launch.bat`**：它会把一条已填好本项目绝对路径的启动命令放进剪贴板，
粘贴到 Maya 的 **Script Editor**（Python 标签）里回车即可：

```python
import sys; sys.path.insert(0, r"C:\opencode\BatchAttributeEditor"); import main; main.reload_and_launch()
```

该脚本**不会**启动 Maya，只是填好剪贴板，你继续用已经开着的 Maya。它用 `reload_and_launch()`
而不是 `launch()`：Python 会缓存已导入的模块，改完文件后直接 `import main` 拿到的仍是旧代码，
除非重启 Maya；这个命令会先丢弃缓存再重新导入。路径在运行时解析，所以项目放在 U 盘、网络盘、
任意盘符或改名后的文件夹里都能直接用。（命令行窗口里还会打印自检、自动化测试两条命令供手动复制。）

然后：

1. 在视口里选中一个（或多个）节点 —— 例如一个 `Character_GRP`；
2. 在 **属性搜索（Attribute Search）** 里输入 `visibility`；
3. 在 **结果（Results）** 里点中 `visibility   Boolean   182` 这一行；
4. 在 **数值（Value）** 里取消勾选（设为 `False`）；
5. 点 **预览** —— 会看到 `Will modify 175 nodes (175 channels), skip 7`（其中 5 个锁定、2 个已连接）；
6. 点 **应用**；
7. 按一次 `Ctrl+Z` —— 175 个节点全部还原。

安装方式（工具架按钮、复制到 scripts 目录、随 Maya 自动加载）见
[`docs/INSTALL.zh.md`](docs/INSTALL.zh.md)；完整功能说明见 [`docs/USAGE.zh.md`](docs/USAGE.zh.md)。

---

## 支持的类型

| 类型 | 编辑器 | 说明 |
| --- | --- | --- |
| Float / Double | 数值输入 | 支持 Maya 声明的 hard range |
| Integer | 整数输入 | 严格整数校验，不静默取整 |
| Boolean | 复选框 | |
| String | 文本输入 | 绝不当作数值处理 |
| Enum | 下拉框 | 显示枚举名，内部写 Maya 枚举下标 |
| Angle / Distance / Time | 数值输入 + 单位提示 | 按 Maya 工作单位（度 / 厘米 / 帧） |
| Float3 / Double3 | X / Y / Z 三个通道 | 每通道可单独勾选 |
| Color3 | R / G / B + 颜色选择器（Color Picker） | 不擅自 clamp 到 0-1 |
| Compound | 子属性逐项编辑 | 通过 `plug.child(i)` 索引定位，不拼名字 |
| Multi（数组） | 每个已存在的元素一行 | 第一版只编辑已存在的元素 |
| Matrix / Message | 仅识别与查看 | 不假装支持编辑 |

---

## 安全策略

默认**非破坏性**。以下行为**永远不会**自动发生：

* 解除锁定（unlock）
* 断开连接（disconnect）
* 创建 / 删除属性或数组元素
* 隐式类型转换（例如把 float 属性当 int 写、把 String 当数值）
* 删除 / 重命名节点

被锁定、被连接、属性缺失、类型不匹配的目标会被**跳过并给出原因**，
在预览和报告中逐条列出，同时把技术细节（异常类型、plug 名称）保留在日志里。

---

## 项目结构

```
BatchAttributeEditor/      ← 把这个目录加入 sys.path
    __init__.py            可选门面：注入 sys.path 并转发到 main
    bootstrap.py           sys.path 注入与同名模块冲突处理
    main.py                入口：launch() / close() / __version__
    core/                  与 Qt 无关，可在 mayapy 下完整测试
        types.py           类型数据模型（AttributeKind / ChannelSpec / AttributeDefinition）
        type_resolver.py   真实类型识别（MObject + MFn* 元数据）
        selection.py       选择解析与去重
        traversal.py       DAG 遍历（含 Shape / Intermediate）
        attributes.py      属性枚举与类型识别
        compatibility.py   锁定 / 已连接 / 缺失 / 类型兼容校验
        search.py          搜索、匹配、按 (名称, 类型) 聚合
        batch_setter.py    预览与批量写入
        undo.py            Undo Chunk 管理
        cache.py           扫描缓存
        results.py         预览 / 执行结果数据类
        session.py         Core 门面（UI 只与它交互）
    ui/                    只通过 Core 访问 Maya
        qt.py              PySide6 / PySide2 兼容层
        panels.py          范围 / 搜索 / 详情 / 预览 / 日志 区块
        attribute_model.py 结果表模型
        editors/           按类型动态生成的编辑器（ValueEditorFactory）
        main_window.py     窗口编排
    utils/
        maya_utils.py      节点/plug 名称派生、UUID 复查
        logging_utils.py   双通道日志（用户可读 / 技术细节）
    tests/                 142 个测试（mayapy 下运行）
    tools/selfcheck.py     在真实 Maya 里运行的自检脚本
    docs/                  文档（安装 / 使用 / 架构 / 已知限制）
```

扁平结构的代价是 `core` / `ui` / `utils` / `tests` 这些顶层名字很常见，
可能与其他同样采用扁平结构的插件（例如同目录的 `materialConvert`）撞车。启动时工具会：

* 把本项目根**置顶**到 `sys.path`，让本项目的包优先被找到；
* 释放同名顶层模块下所有**来自其它路径的模块（含缓存的子模块）**——例如对方残留的
  `core.results`，否则它会在后续导入时遮蔽本项目；
* 发生接管时打印提示。

由此形成双向可用的「后启动者赢」契约：另一个工具已打开的窗口依靠已导入的模块对象继续工作，
两个工具可以在同一个 Maya 会话中共存。不需要该行为时用 `main.launch(release_conflicts=False)`。

---

## 测试

Core 层与部分 UI 层可在 Maya 自带的 `mayapy` 下完整自动化测试（在项目根目录下运行）：

```powershell
& "C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe" tests\run_tests.py
```

只跑某个模块：

```powershell
& "C:\Program Files\Autodesk\Maya2024\bin\mayapy.exe" tests\run_tests.py -k undo
```

当前结果：**142 个测试全部通过**（其中 12 个需要真实 GUI 的 widget 测试在 batch 模式下跳过）。

| 测试文件 | 覆盖内容 |
| --- | --- |
| `test_traversal.py` | 单 Transform、Transform+Shape、Intermediate Shape、多根、去重、5 层深层级、DG 节点 |
| `test_type_resolution.py` | Float / Int / Bool / String / Enum / Angle / Distance / Time / Float3 / Double3 / Color3 / Compound / Multi / User Defined / Matrix / 缺失属性 / hard range |
| `test_search.py` | 完整/部分/长短名/大小写/模糊匹配、聚合、同名不同类型拆分 |
| `test_compatibility.py` | 锁定、已连接（含连接源可写、compound 子连接）、缺失、类型不匹配、删除节点、重命名节点 |
| `test_batch_setter.py` | 各类型批量写入、颜色不 clamp、multi 不新建元素、缺失/锁定/连接跳过、单点失败不中断整批、同名不同类型只改兼容节点 |
| `test_undo.py` | 一次应用 = 一次撤销、重做、部分失败仍一次撤销、150 节点仍一次撤销、对照组证明 chunk 必要 |
| `test_session.py` | 端到端工作流、预览统计自洽、缓存与刷新、1500+ 节点性能 |
| `test_ui_smoke.py` | UI 模块导入、工厂注册表完整性、结果表模型；widget 测试在 GUI 会话中运行 |

在真实 Maya GUI 里做一次端到端自检（会建临时节点并用完即删）：

```python
import sys
sys.path.insert(0, r"C:\opencode\BatchAttributeEditor")
import tools.selfcheck
tools.selfcheck.run(create_test_nodes=True)
```

---

## 验证状态（诚实说明）

| 部分 | 状态 |
| --- | --- |
| Core（遍历 / 类型识别 / 校验 / 搜索 / 写入 / 撤销） | ✅ 142 个测试在 Maya 2024.2 mayapy 下通过 |
| 撤销粒度（一次应用 = 一次撤销） | ✅ 实测验证（含 150 节点批量与部分失败场景） |
| UI 模块导入与工厂分发 | ✅ 自动化验证 |
| **UI 窗口构建与显示** | ✅ 已在真实 Maya 2024.2 GUI 中确认（`tools/selfcheck.py`，PySide2 5.15.2） |
| **UI 交互细节**（按钮点击、颜色选择器、停靠拖拽） | ⚠️ 未自动化覆盖，需人工体验确认 |

窗口构建与显示的确认过程与结果见 [`docs/LIMITATIONS.zh.md`](docs/LIMITATIONS.zh.md) 第 1 节。
selfcheck 会构建窗口、在临时节点上跑完整流程（含"整批写入只占一次撤销"），最后删除临时节点。

---

## 已知限制摘要

* 第一版不创建 / 删除数组元素，只编辑**已存在**的元素；
* 不提供"强制解锁""强制断开连接"等破坏性选项；
* Matrix / Message 等类型只识别不编辑；
* 默认只递归 DAG 后代，不递归整个 Dependency Graph（扩展位已预留但未启用）；
* 本机色彩管理初始化失败，`cmds.addAttr(attributeType="float3")` 会静默失败 ——
  这是**环境问题**，不影响工具（Color3 用真实颜色属性测试，如 `overrideColorRGB`、`lambert.color`）。

完整列表见 [`docs/LIMITATIONS.zh.md`](docs/LIMITATIONS.zh.md)。

---

## 文档

| 文件 | 内容 |
| --- | --- |
| [`docs/ARCHITECTURE.zh.md`](docs/ARCHITECTURE.zh.md) | 模块职责、数据流、API 策略、撤销策略、实测依据 |
| [`docs/INSTALL.zh.md`](docs/INSTALL.zh.md) | 安装、验证、卸载 |
| [`docs/USAGE.zh.md`](docs/USAGE.zh.md) | 界面与工作流说明 |
| [`docs/LIMITATIONS.zh.md`](docs/LIMITATIONS.zh.md) | 已知限制与注意事项 |
