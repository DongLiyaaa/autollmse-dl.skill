# AutoLLMSE-DL

Cross-platform Markdown memory compression for OpenClaw workspaces.

The project scans `MEMORY.md`, daily memory files, hot memory, and unified summaries, then applies:

- semantic deduplication with an optional embedding model
- importance scoring with safe heuristic fallback
- atomic writes plus rotating backups
- Windows, Linux, and macOS aware encoding handling

## Installation

```bash
pip install .
```

Install optional semantic-search dependencies if you want embedding-based deduplication:

```bash
pip install ".[semantic]"
```

For local development:

```bash
pip install -e ".[semantic]"
```

## Usage

Run against the default OpenClaw workspace:

```bash
python -m autollmse_dl --all
```

Or use the console script installed by the package:

```bash
autollmse-dl --all
```

Common commands:

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

## Configuration

The compressor looks for configuration in this order:

1. `--config /path/to/file.json`
2. `<workspace>/skills/autollmse-dl/config/compression_rules.json`
3. the packaged default at `autollmse_dl/config/compression_rules.json`

Example:

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

## Development

Run tests with the standard library test runner:

```bash
python -m unittest discover -s tests -v
```

## Notes

- If `sentence-transformers` or `numpy` is unavailable, semantic deduplication automatically falls back to lightweight text similarity.
- Backups keep the latest `.bak` file plus timestamped historical versions.
- Writes are atomic to reduce the chance of corrupting memory files during compression.
