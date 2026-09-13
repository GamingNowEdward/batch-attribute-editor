[English](LIMITATIONS.md) | **中文**

# 已知限制

本文件记录**当前版本确实做不到、或做了取舍**的地方，以及背后的实测依据。
每条都尽量给出"为什么"和"怎么绕开"。

---

## 1. 验证覆盖

| 部分 | 状态 |
| --- | --- |
| Core（遍历 / 类型识别 / 校验 / 搜索 / 写入 / 撤销（Undo）） | ✅ 158 个自动化测试在 Maya 2024.2 的 mayapy 下通过（13 个 GUI 测试跳过） |
| 撤销粒度（一次应用 = 一次撤销） | ✅ 实测验证（150 节点批量、部分失败场景） |
| UI 模块导入与工厂分发 | ✅ 自动化验证 |
| 本地化（语言切换 / 回退 / 持久化 / Core 文本） | ✅ mayapy 下自动化覆盖；控件级重译另用 PySide6 6.11（offscreen + fake `maya`）冒烟验证 |
| **UI 窗口构建与显示** | ✅ 已在真实 Maya 2024.2 GUI（PySide2 5.15.2）中确认 |
| **UI 交互细节** | ⚠️ **未自动化验证**（按钮点击、颜色选择器、停靠拖拽需人工体验） |

**窗口构建的实测记录**（`tools/selfcheck.py` 在真实 Maya GUI 会话中的输出）：

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

（`skip 5` 是根节点自身没有 `baeWeight` 属性，属于正确的缺失统计。）

**为什么 widget 级测试不能自动化**：`mayapy` / `standalone` 下无法创建 `QApplication` ——
实测中一旦尝试创建，进程会以 `QWidget: Cannot create a QApplication` 直接退出。
因此 `test_ui_smoke.py` / `test_i18n.py` 里 13 个需要 QWidget 的测试在 batch 模式下被自动跳过，
窗口与交互只能靠真实 GUI 会话确认。（语言切换的重译路径另在 Maya 之外用真实 Qt 应用做过
跨绑定冒烟验证：系统 Python + PySide6 + offscreen 平台，`maya` 包以假实现替代。）

**尚未逐项人工确认的交互**：颜色选择器按钮、只勾选部分通道、过滤器勾选、
停靠到面板后的布局持久化。若发现问题，Script Editor 的输出与
**报告 · 日志（Report · Log）**面板的内容可以直接用于定位。

### 窗口停靠的行为

窗口使用 `MayaQWidgetDockableMixin` + 普通 `QWidget` 实现（**刻意不用 `QMainWindow`**：
带 `Qt.Window` 标志的窗口在 Maya 把它并入标签页时会重建原生句柄，存在崩溃风险）。
默认以浮动窗口打开，可以手动拖入停靠区，也可以用 `launch(dock=True)` 直接停靠到右侧。

工作区布局的持久化（重启 Maya 后窗口位置是否恢复）**未做专门处理**，属于未验证范围。

---

## 2. Multi / 数组属性

* **只编辑已经存在的数组元素**，不会创建新元素、不会删除元素、不会自动扩展数组；
* 一个属性在不同节点上的数组索引集合可能不同（`input[0]` 只在部分节点存在）。
  编辑器取**并集**列出所有通道；写入时逐节点重新校验，
  在某个节点上不存在的元素会被计为「数组元素不存在」并跳过；
* `setNumElements` 之类的结构性操作不在支持范围内。

**为什么**：需求明确第一版只要求编辑已存在元素；创建/删除元素属于结构性修改，
风险更高（会改变拓扑与历史），需要单独设计确认流程。

---

## 3. 不支持编辑的类型

| 类型 | 状态 |
| --- | --- |
| Matrix | 只识别与展示，不提供编辑器 |
| Message | 只识别与展示（它是连接用的占位属性，没有可写的值） |
| 2 分量复合数值（k2Float / k2Double） | 归入 Compound，按其子属性逐项编辑 |
| Generic / 插件自定义数据类型 | 识别为 Unknown，不提供编辑器 |

这些属性会出现在搜索结果里（除非勾选"隐藏不支持的类型"），
但选中后数值（Value）区会说明"暂不支持编辑"，而不是给出一个会写错的控件。

---

## 4. 安全相关的刻意取舍

以下操作**永远不会自动执行**，当前版本也**没有**提供开关：

* 解除属性锁定（`lock=False`）
* 断开已有连接（`disconnectAttr`）
* 创建 / 删除属性或数组元素
* 隐式类型转换（float 当 int 写、String 当数值写等）
* 删除或重命名节点

被锁定或被连接的目标会被跳过并给出原因。如果确实需要改这类属性，
请先手动解锁 / 断开（这是有意的摩擦：让破坏性操作必须由人明确发起）。

---

## 5. 搜索范围的限制

* 默认只递归 **DAG 后代**（Transform、Shape、Intermediate Shape）。
* **不会**递归整个 Dependency Graph。原因：DG 可能极其庞大，而且会把不属于当前层级的
  节点（history、utility、shader 网络）都卷进来。
* 选中非 DAG 节点（例如一个 lambert 材质）时，只扫描该节点自身 —— 这是正确行为，
  但意味着"选中着色器批量改颜色"需要把相关节点都选上。
* 代码里为 `TraversalScope` 预留了 `DEPENDENCY_CONNECTIONS` / `HISTORY` / `REFERENCED`
  等扩展位，但**未实现**，默认绝不会偷偷启用。

---

## 6. 单位属性的处理

* Angle / Distance / Time 按 **Maya 当前工作单位**显示与输入（默认：度 / 厘米 / 帧），
  与 `cmds.getAttr` / `cmds.setAttr` 的单位一致；
* 如果用户把工作单位改成英寸或弧度，界面上的数字随之改变（这是 Maya 的语义）；
* 单位属性的 hard range 会按度 / 厘米 / 帧换算后显示，仅用于提示，**不用于 clamp**。

---

## 7. 缓存

* 扫描缓存只在搜索阶段使用；**应用（Apply）时一律重新解析 plug 并重新校验**，
  所以即便缓存过期，最坏情况是搜索结果显示陈旧，**不会写错节点**。
* 失效时机：显式刷新、场景新建/打开、撤销/重做。
* 自动跟随选择（切换选中节点）只重新解析选择，**不清缓存**（选择变化不影响属性表），
  因此切换选择很快。
* 已知缺口：通过脚本直接 `addAttr` / `deleteAttr` 增删属性**不会**触发缓存失效
  （Maya 没有轻量的"属性表变化"通知）。此时点一次 **刷新选择（Refresh Selection）** 即可。

---

## 8. 环境相关的已知问题（本机实测）

这些是**运行环境**的问题，不是工具缺陷，但会影响测试夹具的搭建：

| 现象 | 实测结果 | 影响 |
| --- | --- | --- |
| 色彩管理初始化失败 | `OCIO profile Z:\ocio\...` 读不到，`colorManagementPrefs -cmEnabled` 为 `False` | 无（工具不依赖色彩管理） |
| `cmds.addAttr(attributeType="float3")` | **静默失败**：不抛异常，但属性不会被创建 | 无法用脚本创建 Color3 测试属性；测试改用真实存在的颜色属性（`overrideColorRGB`、`lambert.color`） |
| `cmds.addAttr(attributeType="Float3")` | 明确报错 `Type specified for new attribute is unknown` | 同上 |
| `MFnNumericAttribute.createColor(name, kFloat)` | `TypeError: argument 2 must be str, not int` | 同上 |

> 如果需要在场景里新建 Color3 属性，请用 Attribute Editor 的
> `Add Attribute → Color` 或正常的 `addAttr -at float3` 流程；
> 工具本身对 Color3 的**识别与写入**已在真实颜色属性上验证通过。

其他实测到的 Maya API 陷阱（已在代码里规避，记录备查）：

* 节点删除后，旧 `MObject` 的 `isNull()` 仍返回 `False`，且
  `name()` / `attributeCount()` / `findPlug()` 会继续返回**陈旧数据而不报错** ——
  因此所有复查都通过 **UUID** 重新定位节点；
* `MFnDependencyNode.uuid()` 在 API 2.0 返回的是 `MUuid` **对象**而不是字符串，
  必须转成字符串才能交给 `cmds.ls`；
* `MPlug.isConnected` 对连接的**源端**同样是 `True`，只有 `isDestination` 才代表写入无效；
* compound 父 plug 在只有子 plug 被连接时 `isConnected` 仍为 `False`
  （要靠 `numConnectedChildren()` / `isFreeToChange()` 才能发现）；
* `MPlug` 的 setter 写入**不进入撤销队列**（实测连续 5 次写入后 `undo()` 直接失败），
  所以写入统一走 `cmds.setAttr`；
* `cmds.ls(node, shapes=True)` 在本版本返回空列表，遍历必须用 `MItDag`；
* `undoInfo(query=True, length=True)` 返回的是队列**容量**而非条目数。

---

## 9. 版本兼容性

* 开发与测试均在 **Maya 2024 / 2024.2 + Python 3.10 + Maya API 2.0** 上完成。
* Maya 2022 / 2023 **预期可用但未实测**：代码只依赖 API 2.0 与长期稳定的 `cmds`；
  2.0 API 从 Maya 2016 起就已提供。
* Maya 2025 / 2026 **未实测**。主要风险点是 Qt 版本（PySide6 已支持）与
  `mayaMixin` 的行为差异。
* 若在其它版本上遇到问题，`tools/selfcheck.py` 会打印出具体的模块与异常，
  便于定位。

---

## 10. 尚未实现（需求中列为"未来扩展"）

以下能力在架构上预留了位置，但**当前版本没有实现**：

* 批量创建 / 删除 / 复制 / 比较属性
* 批量保存与加载属性预设（Attribute Presets）
* 属性搜索历史
* Dependency Graph 搜索、Namespace 过滤、Node Type 过滤
* 断开连接后强制写入、强制解锁等破坏性高级选项
* 数组元素的创建与删除
* 后台线程扫描（目前搜索是同步的，超大场景会短暂阻塞界面，期间显示等待光标）

---

## 11. 本地化（界面语言）

* 目前只提供 **English 与简体中文**。新增语言 = 增加一份与英文 reference key 集合完全一致的
  词条（注册进 `i18n/manager.py`）并在选择器中加一项，无需改动 UI 代码。
* **审计日志条目保留写入时的语言**——它们是对已发生操作的记录；切换后新产生的条目使用新语言。
  当前显示的预览 / 应用报告、状态栏与详情会立即刷新。
* **已渲染出的输入校验错误**（例如 `通道: <转换错误>`）在切换语言后保持原文本；
  重新触发一次操作即会以新语言渲染。
* **类型标签按设计保持英文**：`Float`、`Double3`、`Compound`、`Matrix` 等视为 Maya 类型名，
  不进入翻译；Technical Details 中的 `type=/api=/numeric=` 元数据行同样保持原样。
* 语言偏好是**按用户全局存储**的（通过 `QSettings`），不区分场景或 Maya 版本，
  在下次 `launch()` 时恢复。
* 切换语言是**原地刷新**打开的窗口——不会重建控件，因此当前表格选择、编辑器输入与日志历史
  都会保留。如果第三方直接调用 `i18n.set_language()`，已打开的窗口不会自动收到通知；
  请使用窗口内的选择器。
