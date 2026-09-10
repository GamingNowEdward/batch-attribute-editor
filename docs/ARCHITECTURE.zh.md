[English](ARCHITECTURE.md) | **中文**

# Batch Attribute Editor — 架构说明

> Maya 批量属性发现与编辑系统（Maya Batch Attribute Discovery & Editing System）
>
> 目标 Maya 版本：**Maya 2024（2024.2 实测）/ Python 3.10 / API 2.0**
> 本文档中的每一条 API 结论都在本机 mayapy 上实测验证过，来源见 `tests/` 与第 9 节。

---

## 1. 产品目标

在用户选中的节点层级中，递归发现节点、按名称搜索属性、识别属性的**真实 Maya 类型**，
为不同类型生成对应编辑器，安全跳过锁定（Locked）/ 已连接（Connected）/ 缺失（Missing）/
类型不兼容属性，一次应用（Apply）完成批量修改，并且**整批修改只占一次撤销（Undo）**。

核心不是 `for node: cmds.setAttr(...)`，而是：

```
Hierarchy Traversal → Attribute Discovery → Type Resolution
→ Compatibility Validation → Type-aware Editing → Batch Apply → Undo/Redo
```

---

## 2. 分层与数据流

项目采用**扁平结构**：`core` / `ui` / `utils` / `tests` 直接位于项目根目录，
把项目根加入 `sys.path` 后即可 `import main`。入口与引导层：

```
bootstrap.py    项目根置顶 + 顶层同名模块（core / ui / utils…）冲突接管与释放（含其缓存的子模块）
main.py         launch() / close() / reload_and_launch()，窗口生命周期与 scriptJob 回收
__init__.py     可选门面：注入 sys.path 后转发到 main（支持 import BatchAttributeEditor）
```

> 扁平结构的代价是 `core` / `ui` / `utils` 这些顶层名字很常见。`bootstrap` 会把项目根
> 置顶到 `sys.path`，并默认释放同名顶层模块下所有**来自其它路径的模块及其缓存的子模块**
> （例如别的工具残留的 `core.results`，否则会遮蔽本项目的导入）；发生接管时打印提示。
> 该接管与其它扁平结构工具（如 `materialConvert`）对称：**后启动者赢**，已运行的工具
> 依靠已导入的模块对象继续工作。

```
UI Layer (PySide6 / PySide2)
  main_window.py            编排：只调用 Core，不直接操作 Maya 节点
  panels.py                 范围 / 搜索 / 详情 / 预览 / 日志 区块
  attribute_model.py        搜索结果 → Qt 表格模型
  editors/*                 按属性类型动态生成的编辑器（ValueEditorFactory）
        │  （只调用 Core 的公开 API，不出现 cmds.setAttr）
        ▼
Core Layer
  session.py        BatchAttributeSession 门面：UI 的唯一入口
  selection.py      SelectionManager      选择节点解析、去重、决策"根基点"
  traversal.py      DAG traversal         递归收集后代（含 Transform / Shape / Intermediate）
  attributes.py     AttributeScanner      枚举节点属性、按名称搜索
  types.py          数据模型              AttributeKind / ChannelSpec / AttributeDefinition（纯数据）
  type_resolver.py  TypeResolver          属性真实类型识别 + 通道构建（MObject / MPlug）
  compatibility.py  CompatibilityValidator 存在性/可写/锁定/连接/类型兼容判定
  search.py         SearchEngine          按 (名称, 类型) 聚合结果 + 统计
  batch_setter.py   BatchSetter           预览与执行批量写入
  undo.py           UndoManager           Undo Chunk 管理
  cache.py          ScanCache             扫描缓存与失效
  results.py        结果数据类            Preview / ApplyReport（纯数据）
        │
        ▼
Utils
  maya_utils.py     节点/plug 名称派生、UUID 复查、DAG 判定等底层封装
  logging_utils.py  双通道日志（UI 友好信息 / 技术细节）
```

**一条完整的数据流：**

```
用户选择节点
  → SelectionManager.resolve()      得到 Unique Root Set（去重）
  → DagTraversal.collect()          得到 NodeRecord 列表（含 Shape）
  → AttributeScanner.scan()         得到每个节点上的属性元数据
  → SearchEngine.search(pattern)    得到 AggregatedAttribute 列表（按类型分组）
  → 用户选中某项
  → CompatibilityValidator.validate() 得到每个节点的 ValidateResult
  → ValueEditorFactory.create()     按 kind 生成编辑器
  → BatchSetter.preview()           得到 PreviewReport（将修改 N / 跳过 M + 原因）
  → BatchSetter.apply()             在一个 Undo Chunk 内写入，得到 ApplyReport
```

---

## 3. 节点遍历策略

* **默认范围**：当前选择 + 其全部 DAG 后代（`MItDag` 深度优先）。
* 必须是 **DAG 后代**，因此包含 Transform、Shape、**Intermediate Shape**。
* 非 DAG 节点（如 shader、utility）被选中时：只扫描该节点自身（它没有后代），
  遍历器显式区分 `MFnDagNode` 与 `MFnDependencyNode`，不会因缺少 DAG path 而失败。
* **不**默认递归整个 Dependency Graph。DG 搜索（connections / history / referenced nodes）
  作为显式扩展点保留在 `traversal.py` 的 `TraversalScope` 中，默认不启用。

**实测依据（probe 1）：**

| 调用 | 结果 |
| --- | --- |
| `cmds.ls(node, shapes=True)` | **返回 `[]`** —— 该写法在此 Maya 版本下不可用 |
| `cmds.listRelatives(node, shapes=True)` | 返回全部 shape（含 intermediate） |
| `MItDag(kDepthFirst, kInvalid)` + `getPath()` | 正确给出 depth / fullPathName / 节点类型 |

> `MItDag` 的 filter 参数**不能**单独用作类型过滤：用 `kMesh` 过滤时根 transform 仍会被返回。
> 因此类型判定一律基于 `path.node().hasFn(...)`，而非迭代器 filter。

---

## 4. 属性数据模型

三个层次，职责分离：

| 类 | 含义 | 生命周期 |
| --- | --- | --- |
| `AttributeDefinition` | 属性的**定义**（类型、约束、单位、枚举字段、子属性） | 每次扫描产生，可缓存为纯数据 |
| `AttributeOccurrence` | 属性在**某个节点上的一次出现**（node、plug 名称、locked/connected/exists） | 每次校验产生 |
| `AggregatedAttribute` | 搜索结果的**一行** = (name, kind) 分组 + 全部 occurrence + 统计 | 每次搜索产生 |

**同名不同类型**天然被建模为不同的 `AggregatedAttribute`：分组键是 `(name, kind)`，
因此 `nodeA.someAttr(float)` 与 `nodeB.someAttr(integer)` 是两个独立结果行，用户选定其一后
只修改该类型兼容的节点，其余进入跳过报告——不做任何隐式类型转换。

`AttributeKind` 取值：
`FLOAT / DOUBLE / INT / BOOL / STRING / ENUM / ANGLE / DISTANCE / TIME /
VECTOR3 / COLOR3 / COMPOUND / MULTI / MATRIX / MESSAGE / UNKNOWN`

---

## 5. 类型识别（TypeResolver）

**绝不通过 `cmds.getAttr()` 的返回值猜类型。** 依据 `MObject` + `MFn*` 元数据判定。

### 5.1 实测的 API 形态（API 2.0，Maya 2024）

这些细节极易写错，全部实测确认：

| 成员 | 形态 | 说明 |
| --- | --- | --- |
| `MFnAttribute.name` / `.shortName` | **属性** | 不是方法 |
| `MFnAttribute.dynamic` | **属性** | 判断"用户自定义属性"用这个，**没有** `userDefined` |
| `MFnAttribute.keyable/.writable/.readable/.hidden/.connectable/.storable` | **属性** | |
| `MFnAttribute.usedAsColor` | **属性** | Color3 判定的关键 |
| `MFnNumericAttribute.numericType()` | **方法** | |
| `MFnNumericAttribute.default` / `.usedAsColor` | **属性** | |
| `MFnNumericAttribute.hasMin()/getMin()/hasMax()/getMax()` | **方法** | 无 min 时 `getMin()` 抛异常，必须先问 `hasMin()` |
| `MFnUnitAttribute.unitType()` | **方法** | `kAngle=1 kDistance=2 kTime=3` |
| `MFnUnitAttribute.default` / `.hasMin()` / `.getMin()` | 属性 / 方法 / 方法 | `getMin()` 返回 `MAngle`/`MDistance`/`MTime` |
| `MFnEnumAttribute.fieldName(i)` | **方法**，接受 int | 返回字段名 |
| `MFnEnumAttribute.fieldValue(s)` | **方法**，接受 **str** | 传 int 会 TypeError |
| `MFnTypedAttribute.attrType()` | **方法** | 返回 `MFnData` 类型（`kString=4` 等） |
| `MFnCompoundAttribute.numChildren()/child(i)` | **方法** | |
| `MFnMatrixAttribute.matrixType` | **不存在** | 矩阵只能用 `apiTypeStr` 判断 |
| `MPlug.isLocked/isConnected/isDestination/isSource/isCompound/isArray/isNull/isDynamic/isKeyable` | **属性** | |
| `MPlug.numChildren()/numElements()/child(i)/elementByLogicalIndex(i)` | **方法** | 非 compound 调 `numChildren()` 抛 TypeError |
| `MPlug.isFreeToChange()` | **方法** | `0=kFreeToChange 1=kNotFreeToChange 2=kChildrenNotFreeToChange` |
| `MPlug.isMulti` | **不存在** | 判断数组用 `isArray` |

### 5.2 各类型判定规则

| AttributeKind | 判定条件 |
| --- | --- |
| `BOOL` | `kNumericAttribute` + `numericType()==kBoolean` |
| `FLOAT` / `DOUBLE` | `numericType()==kFloat` / `kDouble` |
| `INT` | `numericType()` ∈ {`kLong`,`kShort`,`kByte`,`kInt`,`kChar`} |
| `ENUM` | `attr.hasFn(kEnumAttribute)`；字段用 `fieldName(i)` 枚举 |
| `STRING` | `kTypedAttribute` + `attrType()==kString` |
| `ANGLE`/`DISTANCE`/`TIME` | `attr.hasFn(kUnitAttribute)` + `unitType()` |
| `COLOR3` | `apiTypeStr ∈ {kAttribute3Float, kAttribute3Double}` **且** `MFnAttribute(attr).usedAsColor == True` |
| `VECTOR3` | 同上但 `usedAsColor == False`（例如 `translate`，`apiTypeStr=kAttribute3Double`） |
| `COMPOUND` | `attr.hasFn(kCompoundAttribute)` 且非上面两类 |
| `MULTI` | `plug.isArray == True`（在 scalar 类型之外单独标注 `is_multi`） |
| `MATRIX`/`MESSAGE` | `apiTypeStr` 判定，仅可识别/展示，不提供编辑器 |

**实测确认的真实 Color3**：`transform.overrideColorRGB`、`transform.objectColorRGB`、
`lambert.color` 均为 `kAttribute3Float` + `usedAsColor=True` + `plug.isCompound=True` + 3 个子 plug。

**子属性一律用 `plug.child(i)` 索引访问，不拼名字**：实测中同一个 `color` 的子属性名
分别是 `colorR/G/B`、`overrideColorR/G/B`、`objectColorR/G/B`——名字随属性而变，
索引才是稳定结构。另外 `translate` 的子属性 `translateX/Y/Z` 实际是 `kDoubleLinearAttribute`
（单位属性），这也只能靠元数据发现。

### 5.3 属性存在性检测（重要）

实测：**`findPlug("不存在的属性", False)` 会抛 `RuntimeError: (kInvalidParameter)`**，
不会返回空 plug；而 `dep.attribute(name)` 不抛异常，返回一个 `isNull()==True` 的 `MObject`。

因此存在性检测统一为：

```python
attr = dep.attribute(name)          # 不抛异常
if attr.isNull():                   # MObject.isNull() 是方法
    → 属性不存在
```

属性枚举用 `dep.attributeCount()` + `dep.attribute(i)`；`findPlug(MObject, False)` 在属性
存在时安全。`findPlug` 只在这些前提下使用，绝不用于探测存在性。

---

## 6. 写入机制与撤销（本项目的关键决策）

### 6.1 实测结论

| 写入方式 | 是否进入撤销队列 |
| --- | --- |
| `MPlug.setFloat/setInt/setBool/setString/...` | **否**（连续 5 次写入后 `undo()` 立即失败，pops=0） |
| `cmds.setAttr(...)` | **是**（5 次写入 = 5 次撤销，pops=5） |
| `cmds.setAttr` 包在 `undoInfo(openChunk/closeChunk)` 内 | **整块 = 1 次撤销**（50 次写入，pops=1） |
| 块内混有失败写入 | 成功的部分仍然**整块 1 次撤销**（pops=1） |

**因此：写入统一使用 `cmds.setAttr`，并且整批包在一个 Undo Chunk 里。**

### 6.2 为什么这不违反"底层基于 MPlug"

需求要求"不要用字符串拼接 `translateX/translateY/translateZ` 作为唯一数据模型"，
以及"底层优先基于 MPlug"。本项目遵守其精神，做法是分工：

* **发现、类型识别、可行性判定**：100% 基于 `MObject` / `MPlug` 结构（`plug.child(i)`、`plug.elementByLogicalIndex(i)`）。
  数据模型中保存的是 `MPlug` 派生的**真实结构信息**，不是猜出来的名字。
* **写入时的目标名**：由 `MPlug` 自身导出，而非拼接：

  ```
  qualified = dagPath.fullPathName() + "." + plug.partialName(includeNodeName=False, useLongNames=True)
  ```

  实测该方案给出权威且正确的目标：
  `CubeA.w1`、`CubeA.warr[3]`（数组元素）、`CubeA.translateX`（compound 子属性）、
  `CubeAShape.visibility`（shape），且 `cmds.setAttr` 对这些名称全部写入成功。

选择 `cmds.setAttr` 的第二个理由：**错误信息可诊断**。
对锁定属性，API setter 只给出 `RuntimeError: (kFailure): Unexpected Internal Failure`，
而 `cmds.setAttr` 给出 `setAttr: The attribute 'CubeA.lk' is locked or connected and cannot be modified.`
后者可以直接呈现给用户，符合"UI 显示可理解信息、日志保留技术细节"的要求。

### 6.3 Undo Chunk 管理

* `UndoManager.chunk()` 作为上下文管理器：进入 `undoInfo(openChunk=True, chunkName=...)`，
  退出 `undoInfo(closeChunk=True)`。
* 实测 `closeChunk` 在没有打开 chunk 时**静默成功**（不抛异常），因此**绝不**使用
  "循环 closeChunk 直到异常"的写法（那会挂住 Maya 主线程）。
* 块内任何单个写入失败都被捕获并记录，**不中断整批**，也不影响该块的撤销完整性。
* 已知限制：在 commandPort / 无完整事件循环的上下文里，从 Qt 回调内触发的撤销队列可能不可靠
  （兄弟项目 `attributeManager_maya` 亦记录过同类现象）。真实 GUI 交互下的撤销需人工确认，
  自动化测试覆盖到 mayapy 层面为止。

---

## 7. 安全与兼容性策略

默认非破坏性。**绝不**自动执行：unlock、disconnect、删除连接、创建/删除属性、改属性定义、
删除或重命名节点、以及任何隐式类型转换。

判定顺序（`CompatibilityValidator`）：

| 状态 | 判定依据 | 默认行为 |
| --- | --- | --- |
| 缺失 | `dep.attribute(name).isNull()` | 跳过，计入缺失 |
| 不可读 | `MFnAttribute.readable == False` | 跳过 |
| 不可写 | `MFnAttribute.writable == False` | 跳过 |
| 锁定 | `plug.isLocked == True` | 跳过并报原因（不自动 unlock） |
| 已连接 | `plug.isConnected` 或 `plug.numConnectedChildren() > 0` 或 `isFreeToChange()!=0` | 跳过并报原因（不自动断开） |
| 类型不兼容 | 该节点上属性的 `AttributeKind` ≠ 用户选定项的 kind | 跳过，不做隐式转换 |
| Multi 元素缺失 | `elementByLogicalIndex(i).isNull()` | 跳过（第一版不创建数组元素） |

**Compound/multi 的注意事项（实测）**：compound 父 plug 在只有子 plug 被连接时，
`isConnected` 仍是 `False`，而 `isFreeToChange()` 返回 `2 (kChildrenNotFreeToChange)`。
因此判定必须同时看 `isFreeToChange()` 与子 plug，只看父 plug 会漏判并导致写入失败。

---

## 8. 性能策略

实测（2100 个后代节点、约 48 万条属性）：

| 阶段 | 耗时 |
| --- | --- |
| `MItDag` 收集全部 DAG path | 0.003 s |
| 全属性名扫描 | 0.56 s |
| 定位目标 plug | 0.54 s |
| 900 次 chunked `cmds.setAttr` | 0.013 s |

结论：**瓶颈在属性元数据扫描（约 0.27 ms/节点），写入几乎免费。**

策略：

1. `ScanCache` 缓存"每个节点的属性名 → 轻量类型摘要"（纯 Python 数据，**不持有 MObject**）。
2. **正确性优先**：缓存只服务于搜索阶段；应用阶段一律**重新解析** plug 并重新校验，
   因此过期缓存永远不会导致错误写入，最坏情况只是搜索结果显示陈旧。
3. 失效时机：场景新建/打开/导入/引用变化、撤销/重做、节点增删，以及缓存命中时的
   **节点数量校验**（`cmds.ls` 计数很便宜）不匹配即失效。
4. UI **自动跟随 Maya 选择**（`SelectionChanged` scriptJob + 约 350 ms 防抖）：仅选择变化时
   重新解析并搜索，但**保留扫描缓存**，因此大场景下也近乎瞬时；选择集合未变与纯组件选择
   会被跳过、不触发扫描。显式**刷新选择（Refresh Selection）**按钮用于强制清缓存重扫（例如用脚本改动属性之后）。

MObject 生命周期风险：节点被删除后 MObject 失效。因此缓存内**不保存 MObject**，
并且在应用时对每个节点重新取 `MFnDependencyNode`。

---

## 9. 环境与兼容性记录

| 项目 | 实测值 |
| --- | --- |
| Maya | 2024（`apiVersion 20240200`），2024.2 环境 |
| Python | 3.10.8（mayapy） |
| Qt | 5.15.2（mayapy site-packages 仅含 **PySide2**） |
| 目标 Qt | PySide6 优先、PySide2 回退（GUI 会话），**UI 层不在 mayapy 下做自动化测试** |

已知环境异常（**不影响本工具，但影响测试夹具**）：

* 本机色彩管理初始化失败（`OCIO profile Z:\ocio\...` 不可读，
  `colorManagementPrefs -cmEnabled` 为 `False`）。
* 在此状态下 `cmds.addAttr(attributeType="float3")` **静默失败**（属性不会被创建，不抛异常）；
  `attributeType="Float3"` 则明确报 "Type specified for new attribute is unknown"。
  API 侧 `MFnNumericAttribute.createColor(name, kFloat)` 亦失败（TypeError）。
* 因此 Color3 的测试数据一律使用**真实存在**的颜色属性
  （`transform.overrideColorRGB`、`lambert.color`），而不是动态创建。
  工具本身对这两者的识别与写入均已实测通过。

---

## 10. UI 与 Core 的关系

* UI **不出现** `cmds.setAttr` / `cmds.getAttr` / MPlug 操作；只调用 Core 的公开 API。
* Core 不 import Qt，可在 mayapy 下被完整测试。
* 动态编辑器由 `ValueEditorFactory` 依 `AttributeKind` 生成：
  `FloatEditor / IntEditor / BoolEditor / StringEditor / EnumEditor / VectorEditor /
  ColorEditor / UnitEditor`，全部实现统一的 `ValueEditor` 接口
  （`value()` / `set_value()` / `signal changed`），因此新增类型只需注册一个工厂条目。

---

## 11. 扩展点（预留但默认不启用）

`TraversalScope`（DAG / connections / history / referenced）、
`AttributePreset`（保存/加载预设）、批量创建/删除/复制/比较属性、
Namespace 与 NodeType 过滤、Attribute 搜索历史。

Core 的 `SearchEngine` 与 `BatchSetter` 均以"节点集合 + 属性定义"为输入，
不假设节点来自 DAG 遍历，因此上述扩展不需要改动写入层。
