[English](CHANGELOG.md) | **中文**

# 更新日志

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
