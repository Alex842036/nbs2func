# nbs2func

[English](README.md) | [简体中文](README.zh-CN.md)

**当前版本：v0.1.1**

`nbs2func` 可将 Open Note Block Studio 的 `.nbs` 歌曲转换为 Minecraft Java
版红石音符盒结构。项目提供以 Windows 为主要平台的 Tkinter 向导、完整 CLI、
datapack 构建函数以及兼容 WorldEdit 的 `.schem` 输出。

## 预览状态

这是预览版本。核心生成器、向导 GUI、datapack 输出和原理图输出均可使用，
但项目尚未达到生产就绪状态。`note_based_stereo` 仍采用启发式算法；困难或
非常大的歌曲可能需要大量处理时间和内存。

执行生成的构建函数前，请备份 Minecraft 世界。

## 平台与要求

- Python 3.11 或更高版本。
- `requirements.txt` 中的依赖，包括 `mcschematic` 和 `pytest`。
- Minecraft Java 版；不支持基岩版。
- 主要开发与 GUI 测试平台为 Windows。

`run_gui.bat` 和 `install_requirements.bat` 是 Windows 辅助脚本。GUI 的打开
输出文件夹功能目前仅支持 Windows。Python 源码可能可在 macOS 或 Linux 上
运行，但这些平台的 GUI 行为尚未得到完整验证。

本仓库目前不是可由 pip 安装的软件包。请在项目根目录运行，并设置
`PYTHONPATH=src`。

## Windows GUI 快速开始

1. 安装 Python 3.11 或更高版本。
2. 解压或克隆本仓库。
3. 双击 `install_requirements.bat`。
4. 双击 `run_gui.bat`。

`run_gui.bat` 会切换到项目根目录，将 `PYTHONPATH` 设为 `src`，优先使用
`py -3`，不可用时回退到 `python`。

等价的 PowerShell 命令：

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
python -m nbs2func.gui.app
```

完整向导说明见 [docs/zh-CN/gui.md](docs/zh-CN/gui.md)。

## CLI 快速开始

安装依赖并设置源码路径：

```powershell
python -m pip install -r requirements.txt
$env:PYTHONPATH = "src"
```

使用默认配置生成随附示例：

```powershell
python main.py
```

生成其他歌曲：

```powershell
python main.py path\to\song.nbs
```

选择输出格式或 datapack 构建方式：

```powershell
python main.py path\to\song.nbs --output-format schem
python main.py path\to\song.nbs --output-format both
python main.py path\to\song.nbs --datapack-build-style simple_chain
python main.py path\to\song.nbs --datapack-build-style player_tp
```

运行 `python main.py --help` 查看完整 CLI 选项。

## GUI 工作流程

向导在七个步骤间始终保留同一个 `Nbs2FuncConfig`：

1. 输入
2. 布局
3. 布局选项
4. 模块
5. 输出
6. 摘要
7. 生成

可以从步骤栏返回已完成步骤。摘要页提供配置保存功能和底部的“生成”操作。
生成页显示总进度与当前阶段进度、简洁的结构化日志、输出文件夹操作、
“生成另一个”、“返回”和“完成”。

GUI 与 CLI 调用同一个 `generate_from_config()` 入口，不会启动 CLI 子进程，
也不会解析 CLI 输出。

GUI 支持英文和简体中文。可通过菜单栏的“语言”切换；选择会保存到
`~/.nbs2func/gui_settings.json`，并在下次启动时恢复。切换语言会保留当前
配置、已解锁步骤、当前页中有效但尚未提交的修改，以及已完成的生成结果。
若当前页输入无效，切换会被取消，以便在不丢失草稿的情况下修正。CLI 仍仅
使用英文。

## 输出格式

### `datapack`

写出包含 `pack.mcmeta` 和生成构建函数的完整 datapack，其中包括主结构和
所有已启用模块。

Minecraft 1.14.4 至 1.20.1 使用：

```text
<datapack>/data/<namespace>/functions/<build_function_dir>/...
```

Minecraft 1.21.1 使用：

```text
<datapack>/data/<namespace>/function/<build_function_dir>/...
```

### `schem`

根据 datapack 输出所使用的同一结构化方块计划写出 `.schem`。默认文件名
来自输入 NBS 的主文件名，并保留 Unicode。原理图坐标默认使用
`generation_origin`，也可选择 `min_corner`。

仅输出原理图时只包含主红石结构。启动模块和播放辅助依赖运行时逻辑，因此
不会包含在内；GUI 会阻止这种不兼容组合。

### `both`

写出互补的两种结果：

- `.schem` 包含完整方块结构，包括支持时的模块命令方块及其 NBT。
- datapack 只包含记分板、召唤、执行和实体设置等运行时命令。
- datapack 不会重复主音符盒/中继器结构。
- 盔甲架、矿车等召唤实体不会作为原理图中的存活实体嵌入；运行时命令会
  创建它们。

## Datapack 构建方式

### `simple_chain`

- 将大型命令输出拆分为直接相连的多个 mcfunction 文件。
- 每个文件最多包含 65535 条命令。
- 非最终文件会预留一条命令，用于调用下一个函数文件。
- 不会传送玩家、等待区块、使用玩家传送窗口或在各部分间加入计划延迟。
- 要求目标区域保持加载。
- 适用于较小构建、测试或受控的已加载区域。

### `player_tp`

- GUI 和配置中的默认构建方式。
- 将构建划分为空间窗口。
- 把已配置的构建玩家传送到各窗口。
- 等待附近区块加载，并按计划运行命令部分。
- 会增加辅助命令，并占用更多游戏刻。
- 推荐用于大型结构。

玩家传送构建运行期间，请勿离开维度、断开构建玩家连接或中断构建。

`--no-split-functions` 仍作为 `simple_chain` 的兼容别名保留。新命令应明确
使用 `--datapack-build-style simple_chain` 或
`--datapack-build-style player_tp`。

## 布局模式

### `basic_linear`

将一个选定轨道生成为直线红石结构。主要用于小型结构、解析器检查和调试。
若歌曲中有多个非空轨道，必须指定轨道 ID。

### `track_based_stereo`

根据各 NBS 图层/轨道的音量和声像，为其分配稳定空间位置。支持按轨道拆分
中央声像；基于音轨的立体声布局比基于音符的立体声布局更简单，通常也更可
预测。

### `note_based_stereo`

默认的预览布局。每个音符发声单元会从最终音量和声像取得目标，再执行轨道
槽位候选生成、分配、验证和重试。这是启发式模式：复杂歌曲不保证获得理想
排列，大型输入的计算成本也可能较高。

详细控制与限制见 [docs/zh-CN/modes.md](docs/zh-CN/modes.md)。

## 可选模块

### 启动模块

添加同步启动单元和用于开始生成音乐结构的命令方块。

### 播放辅助

添加基于矿车的播放运行时逻辑、记分板状态、准备/开始控件和移动命令。在
GUI 中，播放辅助依赖启动模块。玩家名称、标签、模块位置及相关高级设置可
通过配置和 CLI 选项调整。

依赖运行时的模块不能与仅 `schem` 输出同时使用。请选择 `datapack` 或
`both`。

## 速度控制

速度控制使用 `core/tempo_control.py` 中共享的时序模型：

- `none`：不计算或应用速度控制行为。
- `report`：默认的安全模式；计算并报告建议的 Minecraft tick rate，但不
  改变世界 tick rate。
- `command`：需要播放辅助，将 tick-rate 命令写入播放开始/重置逻辑。可以
  配置播放后恢复为 20 TPS。

后端：

- `auto` 根据精确 Minecraft 版本配置选择后端。
- 较旧的受支持版本使用兼容 Carpet 的 tick-rate 命令。
- 1.21.1 配置使用受支持的原版 tick-rate 命令配置。

用户仍需具备相应权限和所需模组或服务器能力。并非每个受支持 Minecraft
版本都原生提供 `/tick` 命令。

## 支持的 Minecraft 版本

| 精确配置 | CLI 别名 | Pack format | 构建高度 | 函数目录 | 速度后端 |
|---|---|---:|---:|---|---|
| `1.14.4` | `1.14`, `1.14.x` | 4 | `0..255` | `functions/` | 兼容 Carpet |
| `1.16.5` | `1.16`, `1.16.x` | 6 | `0..255` | `functions/` | 兼容 Carpet |
| `1.18.2` | `1.18`, `1.18.x` | 9 | `-64..319` | `functions/` | 兼容 Carpet |
| `1.20.1` | `1.20` | 15 | `-64..319` | `functions/` | 兼容 Carpet |
| `1.21.1` | `1.21` | 48 | `-64..319` | `function/` | 原版配置 |

别名只选择一个精确配置，不代表对整个补丁版本系列的兼容承诺。配置决定
pack format、构建高度、乐器支持、速度后端、函数目录结构和输出能力。
不支持的乐器或基底方块会令生成失败，不会静默回退。

## 输出与游戏内使用

使用默认命名空间和构建目录时，将生成的 datapack 安装到世界的
`datapacks` 目录，然后运行：

```mcfunction
/reload
/function nbs:build/start
```

使用 WorldEdit 时，请将生成的 `.schem` 放入 WorldEdit 所使用的原理图文件
夹，再按 WorldEdit 命令加载和粘贴。操作前请备份世界。

写入 datapack 前，nbs2func 会替换自己管理的生成构建函数目录。GUI 在复用
已有 datapack 根目录前会询问；CLI 则会自动覆盖。此清理不会移除 datapack
根目录下的其他命名空间。

## 配置文件与 CLI 覆盖

配置优先级为：

```text
default_config()
  -> --config JSON
  -> explicit CLI arguments
```

常用配置命令：

```powershell
python main.py --dump-default-config
python main.py path\to\song.nbs --save-config song-config.json
python main.py --config song-config.json
```

GUI 使用同一套默认值，可加载/保存 JSON 配置文件，并把所得
`Nbs2FuncConfig` 交给共享生成器。仅 CLI 提供的分析与高级诊断控制不会暴露
在向导中。

## 已知限制

- `note_based_stereo` 仍采用启发式算法。
- 非常大的歌曲可能需要大量处理时间和内存。当前布局生成器大体为单线程，
  因此在多核系统上总 CPU 利用率可能看起来较低。
- CPU 密集型生成会与 Tkinter 主线程共享 CPython 的 GIL，因此即使总 CPU
  利用率较低，GUI 也可能短暂无响应。
- 生成期间没有安全的取消操作。
- 简单函数链不会加载区块，也不会在函数文件之间等待。
- 玩家传送构建依赖有效且在线的构建玩家，也可能被中断。
- GUI 测试与打开输出文件夹功能目前以 Windows 为主。
- 原理图不会把召唤实体作为存活实体嵌入。
- 尚未实现手动排列和交互式 2D/3D 编辑。

使用生成结果前请阅读 [docs/zh-CN/known_issues.md](docs/zh-CN/known_issues.md)。

## 文档

- [GUI 指南](docs/zh-CN/gui.md)
- [生成模式](docs/zh-CN/modes.md)
- [架构](docs/zh-CN/architecture.md)
- [已知问题](docs/zh-CN/known_issues.md)
- [更新日志](CHANGELOG.zh-CN.md)
- [示例文件](examples/README.zh-CN.md)
- [English README](README.md)

## 开发与测试

在项目根目录运行完整测试套件：

```powershell
$env:PYTHONPATH = "src"
python -m pytest
```

项目倾向于范围明确且保持输出语义的修改。除非拥有再分发权利，否则不要
提交或发布 NBS 歌曲。

## 路线图

未来可能进行的工作（不承诺发布日期）：

- 手动轨道/分组排列模式；
- 手动覆盖可视化；
- 改进超大型逐音符布局的性能；
- 安全取消或基于进程的生成 worker；
- 打包与可安装版本；
- 更多精确 Minecraft 版本配置；
- 可选的 2D/3D 布局可视化；
- 服务器辅助或 RCON 工作流。

## 许可证

本项目采用 MIT 许可证，见 [LICENSE](LICENSE)。

生成的 datapack、函数和原理图可能包含从输入 NBS 文件衍生的音乐编排。
用户有责任确保有权使用、修改和分发歌曲及生成结果。
