---
name: autollmse-dl
description: Cross-platform intelligent compression of OpenClaw Markdown memory files (MEMORY.md and memory/*.md) for Windows, Linux, and macOS. Preserves critical information while reducing storage footprint through semantic deduplication, importance scoring, and time-based aggregation.
---

# AutoLLMSE-DL Skill

This skill provides intelligent, cross-platform compression of OpenClaw's Markdown memory files, ensuring optimal storage usage while preserving essential information across Windows, Linux, and macOS systems.

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
python -m autollmse_dl.compress --all

# Compress specific file
python -m autollmse_dl.compress --file MEMORY.md

# Preview compression results (no actual changes)
python -m autollmse_dl.preview --all
```

### Automated Integration
- Integrates with OpenClaw heartbeat system
- Runs every 6 hours automatically
- Respects the 10% memory reservation rule
- Batch processing to prevent high concurrency blocking

## Performance Optimizations

- **Memory Reservation**: Enforces 10% memory buffer during processing
- **Batch Processing**: Handles large files in chunks to prevent OOM
- **Parallel Processing**: Multi-threaded compression for multiple files
- **Caching**: Vector embedding cache to avoid redundant computations

## Configuration

Compression rules are defined in `config/compression_rules.json` and can be customized per memory file type:

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