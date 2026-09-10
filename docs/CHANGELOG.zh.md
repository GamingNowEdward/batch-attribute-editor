[English](CHANGELOG.md) | **中文**

# 更新日志

本文件记录项目的所有重要更改。
格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)；在出现首个 tag 之前，
历史条目按日期 + 短 commit hash 标识（`main.__version__` 自初始提交起一直是 `1.0.0`）。

## [未发布] — 2026-09-11

### 更改

- README 的快速开始改为使用 **`copy_launch.bat`** 方式，不再手输
  `sys.path.insert(...)` + `main.launch()`：双击项目根目录下的脚本，把复制到剪贴板的命令
  （已带本项目绝对路径）粘贴到 Maya 的 Script Editor 回车即可。命令调用 `main.reload_and_launch()`，
  会先丢弃本项目的模块缓存再重新导入，因此改完代码无需重启 Maya 即可生效。
  该说明与 [`INSTALL.zh.md`](INSTALL.zh.md) 方式 A 保持一致。涉及 `README.md` 与 `README.zh.md`。

### 新增

- `LICENSE`：项目以 MIT 许可证发布。
- `docs/CHANGELOG.md` 与 `docs/CHANGELOG.zh.md`，用于记录重要更改。

## [0b31bb0] — 2026-09-11

### 更改

- `bootstrap.ensure_on_path()` 现在始终把项目根移到 `sys.path` **最前**（不再只在缺失时插入），
  即使另一个扁平结构的工具此前已把自己的根目录置顶，`core` / `ui` 等名字也仍解析到本项目。
- `bootstrap.release_conflicting_modules()` 会连同**缓存的子模块**一起释放外来同名顶层模块：
  对方残留的 `core.results` 曾在接管后遮蔽本项目的导入。
- 原先延后导入的 `core` / `ui` 移到模块顶部（保留 `base` ↔ `channel_widgets` 循环引用
  与 `main.py` 中有意的 UI 懒加载）。
- README / ARCHITECTURE / INSTALL（中英）记录「后启动者赢」的双向接管契约与
  `materialConvert` 共存说明。

## [f8ea66b] — 2026-09-11

### 更改

- 「Keyable only」过滤改为保留 keyable **或** Channel Box 中显示的属性
  （Arnold 的 `aiExposure` 为 `keyable=False`、`channelBox=True`，这类属性可在 Channel Box 中打关键帧）；
  该过滤默认勾选，tooltip 与 USAGE 同步更新。

### 新增

- `AttributeDefinition.is_channel_box`，经 `MFnAttribute.channelBox` 读取。
- 测试覆盖 channelBox 场景（通过 OpenMaya API 创建，因为 `addAttr` 没有 `channelBox` 标志）。

## [069e2ec] — 2026-09-11

### 新增

- 首个版本（`main.__version__` 1.0.0）：Maya 批量属性发现与编辑 —— 递归层级遍历（含 Shape）、
  按属性名搜索、真实类型识别、兼容性校验（Locked / Connected / Missing / 类型不匹配）、
  按类型生成编辑器、预览与批量写入、一次 Apply 只占一次 Undo。
- `core` / `ui` / `utils` 包结构、mayapy 下运行的 136 个测试、`tools/selfcheck.py`、
  一键 `copy_launch.bat`、README 与 INSTALL / USAGE / ARCHITECTURE / LIMITATIONS 文档（中英）。
