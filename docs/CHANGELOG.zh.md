[English](CHANGELOG.md) | **中文**

# 更新日志

## 2026-09-14

### 修复

- `ui/panels.py`：`SearchPanel` 的过滤器复选框现在等到全部创建完成后才连接 `toggled` 信号 ——
  此前构造期间的 `setChecked(True)` 会在其余复选框创建之前触发 `toggled`（PySide 会打印但吞掉
  该 `AttributeError`）
- `ui/panels.py`：文本交互掩码由裸写的 `| 0x1` 改为 `Qt.TextSelectableByMouse`，使窗口在
  PySide6 / Qt 6 的严格枚举下也能构建

### 新增

- **中英文界面切换（English / 中文）**：窗口右上角新增 `Language:` 选择器；默认 English，
  切换立即生效（无需重启 Maya），原地刷新全部面板、不重建控件；选择通过 `QSettings` 持久化，
  下次启动自动恢复（首次启动默认 English）
- 新增顶层 `i18n/` 包（纯 Python，无 Qt / Maya 依赖，Core 与 UI 均可引用）：
  `manager.py`（词条查找、English 回退、`{参数}` 格式化、`plural()`）、`en.py`（English reference
  词条，与原有英文字面量逐字一致）、`zh_cn.py`（简体中文；key 集合由测试强制与英文一致）
- `ui/settings.py`：`LanguageSettings` —— 一个可注入后端的小型 QSettings 封装
- `tests/test_i18n.py`：29 个测试 —— manager 切换 / 回退 / 格式化 / 复数、词条 key 与占位符
  一致性、源码中字面量 `tr("...")` key 扫描、假后端与真实 QSettings 后端持久化、Core 报告文本、
  以及 GUI 语言切换测试

### 变更

- 所有用户可见文本改为经由 `i18n.tr()` / `i18n.plural()`：窗口标题、区块标题、按钮、tooltip、
  占位符、过滤器、状态栏、属性详情、结果表头、技术详情占位符、预览 / 应用报告、批量写入与
  类型转换错误消息、审计头。英文词条逐字复刻原有字面量，因此既有英文断言与行为完全不变
- 切换语言时会重放窗口持有的动态状态（选择状态、搜索摘要 / 空状态、当前属性详情与校验、
  当前显示的预览 / 应用报告、数值提示），并对已有编辑器调用 `retranslate()`；
  审计日志条目保留写入时的语言
- Maya 数据**刻意不翻译**：节点 / 属性 / plug 名、枚举原始值、类型标签（`Float`、`Double3` 等）、
  `definition.describe()` 元数据与异常文本均保持原样
- `bootstrap.TOP_LEVEL_MODULES` 加入 `i18n`，同名模块接管与 `reload_and_launch()` 覆盖新包

### 文档

- README / ARCHITECTURE / USAGE / INSTALL / LIMITATIONS（中英）补充：本地化架构、语言选择器、
  持久化与重置方式、翻译与 Maya 数据的边界，以及本地化已知限制（审计日志语言、原始校验错误、
  类型标签保持英文）
- 文档中的测试数量更新为 **171**（13 个 GUI 测试在 batch 模式下跳过）：README、INSTALL、
  LIMITATIONS（中英）

## 2026-09-11

### 修复

- **「隐藏复合属性子项」（Hide compound children）过滤器真正生效**：`AttributeDefinition` 新增
  `is_compound_child`（通过 `MPlug.isChild` 读取），`SearchFilters.accepts_definition` 会丢弃
  `translateX` / `customVectorX` 这类子属性并保留其父属性，与 `docs/USAGE.zh.md` 一直以来的描述
  一致；新增两个测试覆盖（类型识别 + 搜索）
- **同一 Maya 会话中其它扁平结构工具占用 `core` / `ui` 时启动不再失败**：
  `bootstrap.release_conflicting_modules()` 现在会连同**缓存的子模块**一起释放外来同名顶层模块
  —— 此前残留的对方 `core.results` 会在接管后遮蔽本项目的导入

### 重构

- `bootstrap.ensure_on_path()` 现在始终把项目根移到 `sys.path` **最前**（不再只在缺失时插入），
  即使另一个扁平结构的工具此前已把自己的根目录置顶，`core` / `ui` 等名字也仍解析到本项目
- 原先延后导入的 `core` / `ui` 移到模块顶部（保留 `base` ↔ `channel_widgets` 循环引用
  与 `main.py` 中有意的 UI 懒加载）

### 新增

- 首个版本（`main.__version__` 1.0.0）：Maya 批量属性发现与编辑 —— 递归层级遍历（含 Shape）、
  按属性名搜索、真实类型识别、兼容性校验（锁定 / 已连接 / 缺失 / 类型不匹配）、按类型生成编辑器、
  预览与批量写入、一次应用只占一次撤销
- `core` / `ui` / `utils` 包结构、mayapy 下运行的测试套件（当时 136 个）、`tools/selfcheck.py`、
  一键 `copy_launch.bat`、README 与 INSTALL / USAGE / ARCHITECTURE / LIMITATIONS 文档（中英）
- `LICENSE`：项目以 MIT 许可证发布
- `docs/CHANGELOG.md` 与 `docs/CHANGELOG.zh.md`，用于记录重要更改
- `AttributeDefinition.is_channel_box`（经 `MFnAttribute.channelBox` 读取），以及 channelBox 场景的
  测试覆盖（通过 OpenMaya API 创建，因为 `addAttr` 没有 `channelBox` 标志）
- UI：匹配模式下拉框的每一项增加 tooltip 说明

### 变更

- 「只显示关键帧属性」过滤改为保留 keyable **或** Channel Box 中显示的属性（Arnold 的
  `aiExposure` 为 `keyable=False`、`channelBox=True`，这类属性可在 Channel Box 中打关键帧）；
  该过滤默认勾选，tooltip 与 USAGE 同步更新

### 文档

- README 的快速开始改为使用 **`copy_launch.bat`** 方式，不再手输 `sys.path.insert(...)` +
  `main.launch()`：双击项目根目录下的脚本，把复制到剪贴板的命令（已带本项目绝对路径）粘贴到
  Maya 的 Script Editor 回车即可；命令调用 `main.reload_and_launch()`，会先丢弃本项目的模块缓存
  再重新导入，因此改完代码无需重启 Maya 即可生效；与 [`INSTALL.zh.md`](INSTALL.zh.md) 方式 A
  保持一致（`README.md` / `README.zh.md`）
- README / ARCHITECTURE / INSTALL（中英）记录「后启动者赢」的双向接管契约与 `materialConvert`
  共存说明
- `docs/USAGE.md` / `USAGE.zh.md`：补全属性搜索参考 —— 匹配模式说明与逐个过滤器详解
  （定义层与逐节点校验、默认值、锁定 / 已连接的「所有节点」规则）；匹配模式表改用能区分
  「包含」与「前缀」的示例，并说明三者的包含关系（完整匹配 ⊆ 前缀 ⊆ 包含）
- 中文文档术语统一：项目自身的 UI / 功能名改用中文，首次出现附英文对照（README.zh、USAGE.zh、
  INSTALL.zh、ARCHITECTURE.zh、LIMITATIONS.zh；ASCII 界面示意图与程序输出保持原样）
- 文档中的测试数量从过时的 136 更新为实际的 **142**（12 个 widget 测试在 batch 模式下跳过）：
  README、INSTALL、LIMITATIONS（中英）
