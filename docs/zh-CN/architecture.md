# 架构

[English](../architecture.md) | [简体中文](architecture.md)

`nbs2func` 为 CLI 和 GUI 使用同一条由配置驱动的生成管线：

```text
CLI or GUI
  -> Nbs2FuncConfig
  -> generate_from_config()
  -> NBS reader
  -> layout strategy
  -> LayoutResult
  -> output.block_builder
  -> GeneratedBuildPlan
  -> scoped plans
       datapack full plan
       schematic structure plan
       both runtime-only plan
  -> command_writer / schematic_writer
```

## 入口与配置

`config.py` 定义 `Nbs2FuncConfig`、默认值、JSON 加载/保存、验证和兼容性
迁移。CLI 的优先级依次为默认值、加载的 JSON、显式参数。GUI 编辑同一个
配置模型。

`generation.py` 通过
`generate_from_config(config, progress_callback=None, include_diagnostics=False)`
负责常规生成编排。它读取歌曲、解析版本配置、验证乐器和速度设置、运行布局、
构建结构化计划、选择输出范围、调用写入器并返回输出路径。

CLI 请求诊断并打印详细的开发者报告。GUI 不请求诊断，只显示结构化进度事件。

## 核心

- `core/models.py` 定义歌曲、轨道和音符。
- `core/nbs_reader.py` 解析 `.nbs` 文件。
- `core/minecraft_version.py` 集中管理精确版本配置、别名、pack format、
  构建高度、函数目录名、乐器支持、原理图能力和速度后端。
- `core/instrument_mapping.py` 将 NBS 乐器映射到 Minecraft 音符盒乐器/基底
  方块，并验证版本支持。
- `core/tempo_control.py` 负责所有速度公式、报告、命令格式、后端选择、限制、
  警告和权限提示。

## 布局

`layout/` 负责放置决策，并返回 `LayoutResult`：

- `facade.py` 暴露策略构造和兼容导入。
- `models.py` 定义布局单元、轨道、发声单元、报告和内部
  `LayoutProgressEvent`。
- `geometry.py`、`pan.py` 和 `collision.py` 提供共享空间规则。
- `basic.py`、`track_stereo.py` 和 `note_stereo.py` 实现三种自动布局策略。

布局代码决定轨道、单元、红石轨道、中继器、音符盒和保留空间的位置，不会
序列化 datapack 或原理图。

## 结构化输出

`output/models.py` 定义 `PlacedBlock`、`GeneratedCommand`、分区和
`GeneratedBuildPlan`。

`output/block_builder.py` 将布局和已解析的写入器/模块配置转换为最终结构化
计划。它负责最终方块 ID/状态、NBT、来源标签、模块方块和非方块运行时命令。
两个写入器都使用这些数据；原理图生成不会解析 mcfunction 文本。

提供四种计划范围：

- **完整：** 结构方块、模块方块和运行时逻辑。
- **仅结构：** 不含模块方块或运行时逻辑的主布局方块。
- **结构与模块方块：** 主结构加模块命令方块，不含仅运行时命令。
- **仅运行时：** 记分板、召唤、执行和实体设置等命令，不含结构/模块方块。

输出映射：

| 格式 | Datapack 计划 | 原理图计划 |
|---|---|---|
| `datapack` | 完整 | 无 |
| `schem` | 无 | 仅结构 |
| `both` | 仅运行时 | 结构与模块方块 |

此映射是稳定性边界：组合输出的 datapack 不能重复主音符盒/中继器结构。

## 写入器

`output/command_writer.py` 将 `GeneratedBuildPlan` 序列化为完整 datapack。
简单函数链使用直接相连的函数文件，每个文件最多 65535 条命令。玩家传送
输出按空间窗口组织命令包，并为传送、等待、各部分及完成函数安排计划。

`output/schematic_writer.py` 将相同的 `PlacedBlock` 值转换为相对原理图坐标，
并通过 `mcschematic` 写入 `.schem`。支持时会保留内联方块状态和命令方块
NBT。表示实体创建的生成命令仍是运行时命令；仅原理图序列化会报告它们被
省略。

写入 datapack 前，`generation.py` 只移除所选命名空间下由 nbs2func 管理的
构建函数目录，不会删除其他命名空间。GUI 会在 datapack 根目录已存在时
确认；CLI 不进行交互，直接执行限定范围的清理和覆盖。

## 模块

`modules/starter.py` 构建同步启动单元、标记设置和启动命令方块。

`modules/playback_assist.py` 构建矿车播放命令方块、记分板逻辑、按钮、移动
命令以及速度开始/重置集成。它使用 `core/tempo_control.py` 的速度报告，
不会重复速度公式。

## GUI

`gui/wizard.py` 负责七步导航外壳、菜单、配置状态、验证、关闭保护和 datapack
覆盖确认。各页面位于 `gui/steps/`。

生成页在后台 Python 线程中启动 `generate_from_config()`。进度回调把不可变
的 `GenerationEvent` 值放入线程安全队列，Tk 的 `after()` 循环排空队列并
更新本地控件：

- 阶段、提示、警告、输出、完成和错误事件会追加到日志；
- 进度事件覆盖当前阶段显示；
- 总进度单调递增；
- 轮询过程不会重建整个页面。

GUI 不运行 CLI 子进程，也不解析标准输出；没有独立的布局、构建计划或写入器
实现。

### GUI 国际化

GUI 文本通过 `gui/i18n.py` 中的 `Translator` 和对应的 `locales/en.json`
或 `locales/zh_CN.json` 解析。所选 GUI 语言与生成配置分开，保存于
`~/.nbs2func/gui_settings.json`。

```text
GUI text -> Translator -> en.json / zh_CN.json
GUI language preference -> ~/.nbs2func/gui_settings.json
GUI or CLI config -> generate_from_config()
```

配置字段名、内部 enum 值和 CLI 行为是与语言无关的稳定性边界，保持英文。
`GenerationEvent.message` 保持英文，作为 CLI 和翻译缺失时的回退；有翻译
键和参数时，GUI 使用它们渲染事件。GUI locale 键缺失时回退到英文。

## CLI 与分析

`cli.py` 负责参数解析、配置优先级、默认配置工具、分析分派和详细诊断报告。
常规生成委托给 `generate_from_config(include_diagnostics=True)`。

`analysis/spatial_analyzer.py` 是只读分析器；它报告空间属性，不改变生成行为。

## 稳定性边界

- 精确 Minecraft 配置决定输出能力和路径。
- 布局负责几何；方块构建器负责最终结构化输出；写入器负责序列化。
- GUI 与 CLI 共享配置和生成编排。
- 组合输出保持仅运行时 datapack 语义。
- 播放辅助使用矿车。
- 速度公式保留在 `core/tempo_control.py` 中。
