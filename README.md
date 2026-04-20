# AutoLLMSE-DL

面向 OpenClaw 工作区的跨平台 Markdown 记忆压缩工具。

项目会扫描 `MEMORY.md`、每日记忆文件、热记忆文件和统一摘要文件，然后执行：

- 基于可选 embedding 模型的语义去重
- 带安全降级策略的重要性评分
- 原子写入与轮转备份
- 兼容 Windows、Linux 和 macOS 的编码处理

## 安装

```bash
pip install .
```

如果你想启用基于 embedding 的语义去重，可以安装可选依赖：

```bash
pip install ".[semantic]"
```

如果你是在本地开发或调试：

```bash
pip install -e ".[semantic]"
```

## 使用方式

针对默认 OpenClaw 工作区运行：

```bash
python -m autollmse_dl --all
```

或者使用安装后提供的命令行脚本：

```bash
autollmse-dl --all
```

常用命令：

```bash
# Preview all changes without writing files
autollmse-dl --all --preview

# Compress a specific file inside the workspace
autollmse-dl --file MEMORY.md

# Point to a custom workspace
autollmse-dl --all --workspace /path/to/workspace

# Use a custom config file
autollmse-dl --all --config /path/to/compression_rules.json
```

### OpenClaw Heartbeat Integration

这个项目的设计目标是在 OpenClaw 中由 heartbeat 直接驱动。推荐接入方式如下：

```bash
autollmse-dl --heartbeat
```

`--heartbeat` 不会再维护一个自己的固定定时器。它会在 heartbeat 每次触发时运行一次，所以如果用户修改了 heartbeat 的频率，这个 skill 会自动跟随新的节奏。

换句话说，调度权完全属于 heartbeat，而这个 skill 只负责在每次 heartbeat 触发时执行一轮压缩。

如果你的 heartbeat 文件支持直接写命令片段，那么可以简化成下面这样：

```bash
# AutoLLMSE-DL: run once whenever heartbeat fires
autollmse-dl --heartbeat
```

`--auto` 仍然保留为兼容旧写法的别名，但推荐优先使用 `--heartbeat`。

## 配置

压缩器会按照下面的优先级顺序查找配置文件：

1. `--config /path/to/file.json`
2. `<workspace>/skills/autollmse-dl/config/compression_rules.json`
3. 包内默认配置 `autollmse_dl/config/compression_rules.json`

示例：

```json
{
  "MEMORY.md": {
    "min_importance_score": 7,
    "max_file_size_kb": 500
  },
  "daily_memory": {
    "aggregate_window_days": 7,
    "importance_threshold": 5
  }
}
```

## 说明

- 如果环境里没有安装 `sentence-transformers` 或 `numpy`，语义去重会自动降级为轻量级文本相似度比较。
- 备份会保留最新的 `.bak` 文件，以及带时间戳的历史版本。
- 写入过程采用原子操作，以尽量降低压缩过程中损坏记忆文件的风险。
