# AutoLLMSE-DL - Cross-Platform Markdown Memory Compressor

Intelligent compression system for OpenClaw's Markdown memory files with full Windows, Linux, and macOS compatibility.

## Features

- **Cross-Platform**: Works identically on Windows, Linux, and macOS
- **Semantic Deduplication**: Removes redundant content using vector embeddings
- **Importance Scoring**: Preserves critical information, removes low-value content
- **Time Aggregation**: Automatically summarizes daily memory into weekly files
- **Safety First**: Automatic backups, validation, and rollback support

## Installation

The skill is automatically available when placed in the OpenClaw skills directory:

```
~/.openclaw/workspace/skills/autollmse-dl/
```

No additional installation required. Dependencies are managed through OpenClaw's existing environment.

## Usage

### Command Line Interface

```bash
# Compress all memory files
python -m autollmse_dl.compress --all

# Compress specific file
python -m autollmse_dl.compress --file MEMORY.md

# Preview results without making changes
python -m autollmse_dl.preview --all

# Run in automatic mode (for heartbeat integration)
python -m autollmse_dl.compress --auto
```

### Integration with OpenClaw Heartbeat

Add to your `HEARTBEAT.md` for automatic execution every 6 hours:

```bash
# AutoLLMSE-DL Memory Compression - Every 6 hours
LAST_COMPRESSION_FILE="/tmp/last_autollmse_dl_timestamp"
MIN_INTERVAL_MINUTES=360

current_timestamp=$(date +%s)
if [ -f "$LAST_COMPRESSION_FILE" ]; then
    last_timestamp=$(cat "$LAST_COMPRESSION_FILE")
    elapsed_minutes=$(( (current_timestamp - last_timestamp) / 60 ))
    
    if [ $elapsed_minutes -lt $MIN_INTERVAL_MINUTES ]; then
        echo "Skipping AutoLLMSE-DL: Last run was ${elapsed_minutes} minutes ago"
        exit 0
    fi
fi

echo "$current_timestamp" > "$LAST_COMPRESSION_FILE"
python -m autollmse_dl.compress --auto --platform $(uname -s | tr '[:upper:]' '[:lower:]')
```

## Configuration

Edit `config/compression_rules.json` to customize compression behavior:

- **MEMORY.md rules**: Control which sections to preserve and importance thresholds
- **Daily memory rules**: Configure aggregation windows and event limits
- **Platform-specific settings**: Adjust for different OS requirements

## Safety Features

### Automatic Backup
Before any compression operation, the system creates a backup with `.bak` extension:
- `MEMORY.md` → `MEMORY.md.bak`
- `memory/2026-04-20.md` → `memory/2026-04-20.md.bak`

### Version Retention
Keeps the last 3 versions of compressed files for easy rollback.

### Atomic Operations
All write operations use temporary files and atomic rename to prevent corruption.

## Performance Considerations

- **Memory Usage**: Reserves 10% of available memory as buffer
- **Batch Processing**: Large files processed in chunks to prevent blocking
- **Parallel Execution**: Multiple memory files compressed simultaneously
- **Caching**: Vector embeddings cached to avoid redundant computation

## Platform-Specific Notes

### Windows
- Handles UTF-8 BOM markers correctly
- Uses Windows-compatible file locking
- Path separators automatically normalized

### Linux/macOS  
- Preserves file permissions and symlinks
- Uses native file locking mechanisms
- Compatible with all common shells (bash, zsh, etc.)

## Troubleshooting

### Common Issues

**File Permission Errors**
- Ensure OpenClaw has write access to the workspace directory
- On Windows, run as administrator if needed

**Encoding Issues** 
- The system automatically handles UTF-8 with and without BOM
- If issues persist, ensure your terminal uses UTF-8 encoding

**Memory Exhaustion**
- The system enforces 10% memory reservation
- For very large memory files, increase system RAM or reduce batch size

### Support
For issues or feature requests, check the OpenClaw documentation or community forums.