# AutoLLMSE-DL

面向 OpenClaw 和同类 Agent 工作区的记忆压缩工具，通过语义去重、重要性评分和压缩重建缓解长对话带来的上下文膨胀与回复失焦问题。

项目会扫描 `MEMORY.md`、每日记忆文件、热记忆文件和统一摘要文件，然后执行：

- 基于 embedding 模型的语义去重
- 带安全降级策略的重要性评分
- 原子写入与轮转备份
- 兼容 Windows、Linux 和 macOS 的编码处理

## 安装

下面这些安装命令默认都在**仓库根目录**执行。

如果你是从 GitHub 拉取项目后再安装，推荐顺序是：

```bash
git clone https://github.com/DongLiyaaa/autollmse-dl.skill.git
cd autollmse-dl.skill
pip install .
```

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

安装完可选依赖后，如果本地还没有 `BAAI/bge-m3`，项目会在首次需要语义去重时自动下载并缓存模型。这是显式设计行为，类似“自动安装运行期模型依赖”。

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

### 系统级自动触发模板

如果目标平台没有像 OpenClaw heartbeat 这样的内建触发机制，推荐使用操作系统自己的定时器，而不是让项目自己维护后台循环。

这类场景下，统一使用普通命令即可：

```bash
autollmse-dl --all
```

如果没有全局安装命令，也可以写成：

```bash
python -m autollmse_dl --all
```

#### macOS: `launchd`

下面这个例子表示每 30 分钟执行一次。把内容保存成 `~/Library/LaunchAgents/com.example.autollmse-dl.plist`：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
  <dict>
    <key>Label</key>
    <string>com.example.autollmse-dl</string>

    <key>ProgramArguments</key>
    <array>
      <string>/bin/zsh</string>
      <string>-lc</string>
      <string>autollmse-dl --all --workspace "$HOME/.openclaw/workspace"</string>
    </array>

    <key>StartInterval</key>
    <integer>1800</integer>

    <key>RunAtLoad</key>
    <true/>

    <key>StandardOutPath</key>
    <string>/tmp/autollmse-dl.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/autollmse-dl.err</string>
  </dict>
</plist>
```

加载方式：

```bash
launchctl unload ~/Library/LaunchAgents/com.example.autollmse-dl.plist 2>/dev/null || true
launchctl load ~/Library/LaunchAgents/com.example.autollmse-dl.plist
launchctl start com.example.autollmse-dl
```

#### Linux: `cron`

下面这个例子表示每 30 分钟执行一次：

```cron
*/30 * * * * /bin/bash -lc 'autollmse-dl --all --workspace "$HOME/.openclaw/workspace" >> /tmp/autollmse-dl.log 2>&1'
```

编辑方式：

```bash
crontab -e
```

#### Linux: `systemd --user`

如果你更偏向 `systemd`，可以用下面这组文件。

`~/.config/systemd/user/autollmse-dl.service`

```ini
[Unit]
Description=AutoLLMSE-DL memory compression

[Service]
Type=oneshot
ExecStart=/bin/bash -lc 'autollmse-dl --all --workspace "$HOME/.openclaw/workspace"'
```

`~/.config/systemd/user/autollmse-dl.timer`

```ini
[Unit]
Description=Run AutoLLMSE-DL every 30 minutes

[Timer]
OnBootSec=2m
OnUnitActiveSec=30m
Unit=autollmse-dl.service

[Install]
WantedBy=timers.target
```

启用方式：

```bash
systemctl --user daemon-reload
systemctl --user enable --now autollmse-dl.timer
systemctl --user status autollmse-dl.timer
```

#### Windows: Task Scheduler

可以在“任务计划程序”里创建一个基本任务，按固定间隔运行下面的命令：

程序：

```text
powershell.exe
```

参数：

```text
-NoProfile -ExecutionPolicy Bypass -Command "autollmse-dl --all --workspace $env:USERPROFILE\.openclaw\workspace"
```

如果你想用命令行创建一个每 30 分钟运行一次的任务，也可以用：

```powershell
schtasks /Create /SC MINUTE /MO 30 /TN "AutoLLMSE-DL" /TR "powershell.exe -NoProfile -ExecutionPolicy Bypass -Command \"autollmse-dl --all --workspace $env:USERPROFILE\.openclaw\workspace\"" /F
```

### 多平台使用建议

- OpenClaw：使用 `--heartbeat`
- 其他平台但需要自动执行：使用系统级调度器 + `--all`
- 其他平台但不需要自动执行：由用户或 agent 手动运行 `autollmse-dl --all`

也就是说，项目本身负责“执行一次压缩”，而“什么时候触发执行”应该交给宿主平台或操作系统。

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

### 真实 LLM 模式

默认情况下，项目仍然使用本地启发式评分，不会发起外部模型请求。

如果要启用真实 LLM 评分与摘要生成，当前支持 OpenAI Responses API。启用方式：

```bash
export OPENAI_API_KEY="your_api_key"
export AUTOLLMSE_DL_LLM_ENABLED=true
```

可选环境变量：

```bash
export AUTOLLMSE_DL_LLM_PROVIDER=openai
export AUTOLLMSE_DL_OPENAI_MODEL=gpt-4o-mini
export AUTOLLMSE_DL_LLM_TIMEOUT=45
export AUTOLLMSE_DL_LLM_MAX_BLOCK_CHARS=1200
```

也可以在配置文件里加入：

```json
{
  "llm": {
    "enabled": true,
    "provider": "openai",
    "model": "gpt-4o-mini",
    "timeout_seconds": 45,
    "max_block_chars": 1200
  }
}
```

启用后，流程会保持不变，但评分阶段会对每个文件批量调用一次真实 LLM，为各个 block 生成：

- 更真实的语义重要性分数
- 是否必须保留的判断
- 用于压缩摘要头的简短总结句

### Embedding 模型下载策略

语义去重使用 `sentence-transformers` + `BAAI/bge-m3`。

默认行为：

- 如果没有安装 `sentence-transformers` / `numpy`，自动回退到轻量级文本相似度
- 如果依赖已安装，但本地没有 `BAAI/bge-m3`，则自动下载模型并缓存到本地
- 如果模型已缓存，则直接复用，不重复下载

相关配置示例：

```json
{
  "semantic_model": {
    "provider": "sentence_transformers",
    "model_name": "BAAI/bge-m3",
    "auto_download": true,
    "local_files_only": false,
    "cache_dir": ".cache/models"
  }
}
```

可选环境变量：

```bash
export AUTOLLMSE_DL_EMBEDDING_PROVIDER=sentence_transformers
export AUTOLLMSE_DL_EMBEDDING_MODEL=BAAI/bge-m3
export AUTOLLMSE_DL_EMBEDDING_AUTO_DOWNLOAD=true
export AUTOLLMSE_DL_EMBEDDING_LOCAL_ONLY=false
export AUTOLLMSE_DL_EMBEDDING_CACHE_DIR="$HOME/.openclaw/workspace/.cache/models"
```

如果你希望只使用本地缓存、绝不联网，可以设置：

```bash
export AUTOLLMSE_DL_EMBEDDING_LOCAL_ONLY=true
export AUTOLLMSE_DL_EMBEDDING_AUTO_DOWNLOAD=false
```

## 说明

- 如果环境里没有安装 `sentence-transformers` 或 `numpy`，语义去重会自动降级为轻量级文本相似度比较。
- 如果依赖已安装但模型尚未缓存，默认会自动下载 `BAAI/bge-m3` 并缓存到本地。
- 如果未启用 LLM，或者 LLM 请求失败，系统会自动回退到本地启发式评分，不会中断压缩主流程。
- 备份会保留最新的 `.bak` 文件，以及带时间戳的历史版本。
- 写入过程采用原子操作，以尽量降低压缩过程中损坏记忆文件的风险。
