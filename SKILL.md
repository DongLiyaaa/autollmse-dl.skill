---
name: autollmse-dl
description: OpenClaw-first memory compression skill designed to run directly from heartbeat. Compresses MEMORY.md and memory/*.md while following the user's current heartbeat cadence automatically.
---

# AutoLLMSE-DL Skill

This skill is designed for OpenClaw heartbeat.

The default operating model is simple:

- heartbeat invokes the skill
- the skill runs once
- the next run happens whenever heartbeat runs again

That means this skill does not own its own schedule. If the user changes heartbeat frequency, this skill automatically follows the new cadence without needing a second timer or extra configuration.

## Recommended Heartbeat Usage

Put this directly in heartbeat:

```bash
python -m autollmse_dl --heartbeat
```

If the environment already exposes the installed console script, this is also valid:

```bash
autollmse-dl --heartbeat
```

## OpenClaw Behavior

When called from heartbeat, the skill should:

- scan the current OpenClaw workspace for `MEMORY.md`, `memory/*.md`, `memory/hot/HOT_MEMORY.md`, and `memory/unified_conversation_summary.md`
- create backups before writing
- compress content safely in a single pass
- exit when finished, without trying to manage its own recurring interval

When the user changes heartbeat from, for example, every 30 minutes to every 2 hours, this skill should simply run at the new heartbeat interval on the next cycle.

## What This Skill Should Not Do

- do not hardcode a fixed interval such as every 6 hours
- do not maintain a separate scheduler that can drift away from heartbeat
- do not require the user to update both heartbeat cadence and skill cadence
- do not skip execution because of an internal timer unless the user explicitly asks for that behavior

## Core Features

### 1. Cross-Platform Compatibility
- **Windows**: Full support with proper path handling, encoding (UTF-8 BOM), and file locking
- **Linux/macOS**: Native support with symlink handling and permission preservation  
- **Unified Codebase**: Single codebase works identically across all three platforms

### 2. Intelligent Compression Strategies
- **Semantic Deduplication**: Uses BAAI/bge-m3 embeddings to identify and remove semantically similar content
- **Importance Scoring**: LLM-driven importance rating (0-10 scale) to prioritize critical information
- **Time-Based Aggregation**: Automatically aggregates daily memory files into weekly summaries
- **Structure Preservation**: Maintains Markdown syntax, headers, lists, and code blocks

### 3. Memory File Types Handled
- **MEMORY.md**: Long-term curated memory compression with section-based rules
- **memory/YYYY-MM-DD.md**: Daily memory aggregation and event summarization  
- **memory/hot/HOT_MEMORY.md**: Real-time deduplication for active session data
- **memory/unified_conversation_summary.md**: Conversation summary optimization

## Safety Guarantees

### Mandatory Backup System
- Automatic `.bak` backup creation before any compression
- Retention of last 3 historical versions
- Atomic write operations to prevent corruption

### Incremental Processing
- Only processes new or modified content since last run
- Prevents reprocessing of already compressed data
- Cross-platform timestamp handling for change detection

### Validation & Rollback
- Post-compression validation of file integrity
- Markdown syntax verification
- Easy rollback to previous versions if needed

## Usage

### Manual Execution
```bash
# Compress all memory files
python -m autollmse_dl --all

# Compress a specific file
python -m autollmse_dl --file MEMORY.md

# Preview compression results (no actual changes)
python -m autollmse_dl --all --preview
```

### Heartbeat Invocation

Use `--heartbeat` when the command is triggered by OpenClaw heartbeat:

```bash
python -m autollmse_dl --heartbeat
```

`--heartbeat` means "run now because heartbeat fired." It does not mean "start an internal recurring timer."

### Manual Invocation

Use `--all` or `--file` when you want to run the compressor outside heartbeat, such as during testing or debugging.

## Heartbeat Integration Notes

- OpenClaw heartbeat is the source of truth for cadence
- this skill follows heartbeat frequency automatically
- `--auto` is supported only as a backward-compatible alias for `--heartbeat`
- no extra interval state is required to keep the skill aligned with heartbeat

## Performance Optimizations

- **Memory Reservation**: Enforces 10% memory buffer during processing
- **Batch Processing**: Handles large files in chunks to prevent OOM
- **Parallel Processing**: Multi-threaded compression for multiple files
- **Caching**: Vector embedding cache to avoid redundant computations

## Configuration

Compression rules are loaded from `autollmse_dl/config/compression_rules.json` by default, or from `<workspace>/skills/autollmse-dl/config/compression_rules.json` when the workspace provides an override:

```json
{
  "MEMORY.md": {
    "keep_sections": ["核心身份", "重要配置", "关键决策", "系统架构"],
    "min_importance_score": 7,
    "time_decay_factor": 0.8,
    "max_file_size_kb": 500
  },
  "daily_memory": {
    "aggregate_window_days": 7,
    "importance_threshold": 5,
    "max_events_per_day": 20
  }
}
```
