---
name: autollmse-dl
description: OpenClaw-first memory compression skill that reduces context bloat with semantic deduplication, importance scoring, and heartbeat-aligned execution.
---

# AutoLLMSE-DL Skill

这是一个面向 OpenClaw 的记忆压缩 skill，用于通过语义去重、重要性评分和压缩重建缓解长对话带来的上下文膨胀与回复失焦问题。核心目标是：

- 扫描 `MEMORY.md`、`memory/*.md`、`memory/hot/HOT_MEMORY.md`、`memory/unified_conversation_summary.md`
- 执行语义去重、重要性评分和压缩重建
- 在 heartbeat 或系统调度器触发时运行一次
- 不自己维护独立定时器

## 推荐接入方式

### OpenClaw heartbeat

直接放进 heartbeat：

```bash
autollmse-dl --heartbeat
```

或者：

```bash
python -m autollmse_dl --heartbeat
```

这里的 `--heartbeat` 语义是：

- heartbeat 触发一次
- skill 执行一次
- 下一次执行时间完全由 heartbeat 决定

如果用户把 heartbeat 从 30 分钟改成 2 小时，这个 skill 会自动跟随新的 cadence。

## 安装

下面这些命令默认都在**仓库根目录**执行。

如果是从 GitHub 拉取后安装：

```bash
git clone https://github.com/DongLiyaaa/autollmse-dl.skill.git
cd autollmse-dl.skill
pip install .
```

如果你想启用 embedding 语义去重：

```bash
pip install ".[semantic]"
```

如果用于本地开发或调试：

```bash
pip install -e ".[semantic]"
```

## 命令用法

```bash
# 压缩整个工作区的记忆文件
autollmse-dl --all

# 只压缩某一个文件
autollmse-dl --file MEMORY.md

# 只预览，不写回
autollmse-dl --all --preview

# 指定工作区
autollmse-dl --all --workspace /path/to/workspace

# 指定配置文件
autollmse-dl --all --config /path/to/compression_rules.json
```

## 自动触发策略

- OpenClaw：使用 `--heartbeat`
- 没有 heartbeat 的平台：使用操作系统调度器 + `--all`
- 不需要自动化时：手动运行 `autollmse-dl --all`

这个项目负责“执行一次压缩”，不负责自己做后台常驻调度。

## Embedding 模型行为

语义去重依赖：

- `sentence-transformers`
- `numpy`
- 模型 `BAAI/bge-m3`

默认行为：

- 如果依赖没安装，回退到轻量级文本相似度
- 如果依赖已安装但本地没有 `BAAI/bge-m3`，首次需要语义去重时会自动下载并缓存模型
- 如果模型已缓存，则直接复用

可以通过配置或环境变量控制：

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

如果你希望只使用本地缓存，不允许联网下载：

```bash
export AUTOLLMSE_DL_EMBEDDING_LOCAL_ONLY=true
export AUTOLLMSE_DL_EMBEDDING_AUTO_DOWNLOAD=false
```

## LLM 评分模式

默认情况下，重要性评分使用本地启发式规则。

如果要启用真实 LLM 评分与摘要生成，当前支持 OpenAI Responses API：

```bash
export OPENAI_API_KEY="your_api_key"
export AUTOLLMSE_DL_LLM_ENABLED=true
```

可选：

```bash
export AUTOLLMSE_DL_LLM_PROVIDER=openai
export AUTOLLMSE_DL_OPENAI_MODEL=gpt-4o-mini
export AUTOLLMSE_DL_LLM_TIMEOUT=45
export AUTOLLMSE_DL_LLM_MAX_BLOCK_CHARS=1200
```

启用后，系统会对每个文件批量调用真实 LLM，用于：

- 给 block 打更真实的语义重要性分数
- 判断是否必须保留
- 为压缩结果摘要头生成简短总结句

如果 LLM 请求失败，会自动回退到本地启发式评分。

## 安全行为

- 写回前先创建 `.bak` 备份
- 旧备份会按数量轮转保留
- 写入使用原子替换，减少文件损坏风险
- 非 Windows 平台尽量保留原文件权限

## 不应该做的事

- 不要写死一个固定周期，比如每 6 小时
- 不要让 skill 自己维护独立 scheduler
- 不要要求用户同时维护 heartbeat 频率和 skill 频率
- 不要把瞬时调试噪音长期保留在压缩结果里
