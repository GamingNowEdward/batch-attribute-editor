[English](USAGE.md) | **中文**

# 使用说明

## 1. 界面总览

> 下图是**实际的英文界面**（UI 语言固定为英文，不随文档语言变化）。

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

## 2. 工作流

### 第 1 步：选择范围

在视口里选中一个或多个节点，然后在 **范围（Scope）** 里选择：

* **当前选择 + 所有后代（含 Shape）**（默认）—— 选中 `Character_GRP` 时，
  它会递归包含下面所有 Transform、Shape 以及 Intermediate Shape；
* **仅当前选择** —— 只处理选中的节点本身。

> 同时选中父节点和它的子节点时，工具会自动去重：子节点不会被处理两次。
> 状态栏会提示「已去重 N 个（被其他根覆盖）」。

工具会**自动跟随 Maya 的选择**：在视口中选择新的节点后自动重新扫描，无需手动刷新。
**刷新选择（Refresh Selection）** 按钮用于强制清空缓存并重扫（例如通过脚本增删属性之后）。

### 第 2 步：搜索属性

在搜索框输入属性名。匹配是**大小写不敏感**的，并且同时匹配 **Long Name 与 Short Name**。
搜索框留空会列出全部属性（浏览模式）。修改输入内容（260 ms 防抖）、切换匹配模式或勾选任一过滤器
都会立即重新搜索，不需要按回车。

| 匹配模式 | 行为 | 例子 |
| --- | --- | --- |
| 包含（Contains，默认） | 名字里含该子串 | `vis` → `visibility` |
| 完整匹配（Exact） | 完全相等 | `visibility` 命中，`vis` 不命中 |
| 前缀（Prefix） | 以该串开头 | `trans` → `translate`、`translateX` |
| 模糊（Fuzzy） | 子序列匹配 | `vsblt` → `visibility` |

搜索结果以**属性为中心聚合**，按涉及节点数从多到少排序：

```
visibility        Boolean   182 个节点
overrideColorRGB  Color3     38
transform         Double3    38
```

如果同一个属性名在不同节点上是**不同类型**，它们会被拆成**不同的行**，
并在"同名其他类型"列提示另有多少节点类型不同。选中其中一行后，
只有类型兼容的节点会被修改 —— 工具不会做任何隐式类型转换。

### 第 3 步：确认详情

点中一行后，**属性详情（Attribute Details）** 会显示这次操作的真实影响面：

```
名称：color          类型：Color3
匹配节点：58         可修改：55
锁定：2              已连接：1            缺失：14
```

* **匹配节点** —— 拥有该属性的节点数；
* **可修改** —— 其中属性可写、未被锁定、没有输入连接、类型兼容的节点数；
* **锁定（Locked）/ 已连接（Connected）** —— 会被跳过的节点及原因（不会自动解锁或断开）；
* **缺失（Missing）** —— 扫描范围内**没有**这个属性的节点数。

### 第 4 步：设置数值

编辑器按属性的**真实 Maya 类型**自动生成：

| 类型 | 界面 |
| --- | --- |
| Boolean | 复选框 |
| Float / Double | 数值输入框（支持 Maya 声明的取值范围） |
| Integer | 整数输入框（输入非整数会标红并阻止应用） |
| String | 文本输入框 |
| Enum | 下拉框（显示枚举名，写入 Maya 的枚举下标） |
| Angle / Distance / Time | 数值输入框 + 单位提示（度 / 厘米 / 帧） |
| Float3 / Double3 | X / Y / Z 三行，每行可单独勾选 |
| Color3 | R / G / B 三行 + 色块 + **颜色选择器（Color Picker）…** |
| Compound | 子属性逐项编辑 |
| Multi（数组） | 每个已存在的元素一行，如 `[0] 值`、`[1] 值` |

几个要点：

* **复合属性每个通道都有独立勾选框**——只想改 G 通道时，取消勾选 R/B 即可，
  不会被统一写掉；
* **颜色不会被 clamp**：如果底层属性允许超出 0-1（例如 HDR 颜色），可以直接输入 `2.5`；
* **「取场景当前值（Load Current Value）」**按钮会把第一个可用节点的当前值读回编辑器（只读操作）；
* 输入非法时输入框会标红，**应用**按钮会被禁用，并在提示区说明原因。

### 第 5 步：预览

点 **预览（Preview）**，不会修改场景：

```
将修改 175 个节点（175 个通道），跳过 7 个 —— 程序实际输出为英文：

```
Will modify 175 nodes (175 channels), skip 7
Skip reasons: 5 Locked, 2 Connected
14 nodes with the same attribute name but a different type (excluded)
```
```

下方会列出**每个通道的「旧值 → 新值」明细**，以及**被跳过的节点与原因**，可以在写入前逐条核对。

### 第 6 步：应用

点 **应用（Apply）** 执行。每个目标在写入前都会**重新校验**（节点是否还在、属性是否仍有效、
是否被锁定或连接、类型是否仍兼容），所以预览之后场景发生变化也不会写错。

结果：

```
```
Succeeded:175  Skipped:7  Failed:0  (175 nodes touched)  Elapsed 12 ms
```
```

### 第 7 步：撤销

按一次 `Ctrl+Z`，**整批修改一次性还原**（不是每个节点撤销一次）。
这是通过 Maya 的 Undo Chunk 实现的，已在 150 节点批量与部分失败场景下实测验证。

---

## 3. 典型用法

### 批量关闭可见性

```
选中 Character_GRP → 搜索 visibility → 数值（Value）取消勾选 → 预览 → 应用 → Ctrl+Z 可整体撤销
```

### 批量改颜色

```
搜索 color → 选中 overrideColorRGB（Color3）
→ 用颜色选择器取色，或直接输入 R/G/B
→ 预览 → 应用
```

### 批量改自定义属性

```
搜索 custom
→ customFloat      Float      12 个节点
   customBool       Boolean    12
   customString     String     12
   customColorRGB   Color3      8
选中某一行 → 工具按该行的类型生成对应编辑器
```

### 只改某个分量

```
搜索 translate → 选中 translate（Double3）
→ 取消勾选 X 与 Z，只保留 Y → 输入值 → 预览 → 应用
```

### 批量改数组元素

```
搜索 input → 选中 input
→ 编辑器列出 [0] 值 / [1] 值 / [2] 值（只列出**已存在**的元素）
→ 只勾选需要改的元素 → 预览 → 应用
```

---

## 4. 过滤器

| 过滤器 | 作用 | 代价 |
| --- | --- | --- |
| 只显示可写（Writable only） | 隐藏 Maya 声明为只读的属性 | 便宜 |
| 只显示关键帧属性（Keyable only） | 只保留可设关键帧的属性（keyable 或显示于 Channel Box，如 Arnold 的 Exposure，默认开） | 便宜 |
| 只显示自定义（User defined only） | 只保留 User Defined（动态添加）属性 | 便宜 |
| 隐藏不支持的类型（Hide unsupported） | 隐藏 matrix / message 等无法编辑的类型（默认开） | 便宜 |
| 隐藏复合属性子项（Hide compound children） | 隐藏 `translateX` 这类子属性，只保留父属性 | 便宜 |
| 隐藏锁定（Hide locked） | 隐藏所有节点上都被锁定的属性 | 需要逐节点校验，节点多时较慢 |
| 隐藏连接（Hide connected） | 隐藏所有节点上都有连接的属性 | 需要逐节点校验，节点多时较慢 |

前五项在扫描属性名时就能判定，几乎不花时间；后两项需要逐节点检查 plug 状态，
因此默认关闭 —— 需要时再打开。

### 过滤器详解

* **只显示可写（Writable only）** —— 隐藏 Maya 声明为只读的属性（`MFnAttribute.writable == False`）。
  "可写"只描述定义：某个节点上它仍可能被锁定或有连接，写入时会被跳过并在预览中说明原因。
* **只显示关键帧属性（Keyable only，默认开）** —— 保留 keyable **或** 显示于 Channel Box 的属性。严格意义上
  channelBox 不算 keyable，但两者都能在 Channel Box 里打关键帧（Arnold 的 `aiExposure` 为
  `keyable=False`、`channelBox=True`）。
* **只显示自定义（User defined only）** —— 只保留 `addAttr` 动态添加的属性，
  隐藏 Maya 内建属性（如 `translate`、`visibility`）。
* **隐藏不支持的类型（Hide unsupported，默认开）** —— 隐藏无法生成编辑器的类型：Matrix / Message / Unknown，
  以及没有子属性的 Compound。
* **隐藏复合属性子项（Hide compound children）** —— 隐藏真正的 compound 子属性（如 `translateX`、
  `customVectorX`）并保留其父属性（`translate`），便于整体使用父属性的 X/Y/Z 编辑器；
  仅仅同名的独立动态属性不受影响。
* **隐藏锁定（Hide locked）** —— 只有当该属性在**所有**匹配节点上都被锁定（或全部可写通道被阻塞）时才隐藏整行；
  只要有一个节点可写，行就保留，锁定的节点会在预览/应用时按原因跳过。
* **隐藏连接（Hide connected）** —— 对输入连接使用同样的"所有节点"规则。判定到通道级，因此也覆盖 Maya
  的一个实测行为：compound 父 plug 在只有子 plug 连接时 `isConnected` 仍为 `False`。

---

## 5. 操作审计（Report · Log）

**报告 · 日志** 面板记录每一次应用的完整审计，并在多次操作之间保留历史（默认最近 20 次）：

```
── intensity · 18 · 12:34:56 · 5 changed / 5 skipped ──
[INFO] |aiAreaLightShape1.intensity: 1 → 18
[INFO] |aiAreaLightShape2.intensity: 1 → 18
[WARNING] |aiAreaLight1.intensity: Attribute missing
```

* 成功写入为常规色、跳过为黄色、失败为红色，批次头为青色；
* 每条记录都带**完整写入目标**（`节点全路径.属性/通道`）与 **旧值 → 新值**；
* 失败条目会自动附带一行 `detail:`（异常类型与完整的 plug 名称）；
* **清空（Clear）** —— 清空历史。

工具**不会静默吞掉任何异常**：失败的通道一定会出现在这里并带原因。

---

## 6. 性能参考

在 Maya 2024.2 / mayapy 下实测（2100 个后代节点、约 48 万条属性）：

| 阶段 | 耗时 |
| --- | --- |
| DAG 遍历 | 0.003 s |
| 首次属性扫描（约 1500 个节点） | 0.5 s 左右 |
| 缓存命中的后续搜索 | 几乎瞬时 |
| 900 次批量写入 | 0.013 s |

搜索框带 260 ms 防抖：连续输入时只在停顿后扫描一次。工具自动跟随 Maya 的选择变化
（约 0.35 秒防抖），切换选择后无需手动刷新；场景发生新建 / 打开 / 撤销 / 重做 时
会自动丢弃缓存并重扫。**刷新选择** 按钮用于强制清空缓存重扫。

---

## 7. 小贴士

* **只改一部分节点**：先缩小选择范围（只选目标子树），再用「仅当前选择」；
* **确认影响面**：应用前先看预览里的「旧值 → 新值」明细与跳过原因；
* **保留现场**：本工具的所有写入都是普通 DG 修改，会出现在撤销队列里，
  一次 `Ctrl+Z` 即可整体回退；
* **同名不同类型的排查**：结果行的"同名其他类型"列不为空时，
  说明场景里还有同名但类型不同的属性，它们会被自动排除（不会被隐式转换）。
