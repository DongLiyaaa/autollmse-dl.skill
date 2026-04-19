"""Command-line interface for AutoLLMSE-DL."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__
from .compressor import MemoryCompressor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compress OpenClaw Markdown memory files.")
    parser.add_argument("--all", action="store_true", help="Compress all detected memory files.")
    parser.add_argument("--file", type=str, help="Compress a specific file inside the workspace.")
    parser.add_argument("--preview", action="store_true", help="Preview compression without writing files.")
    parser.add_argument(
        "--heartbeat",
        action="store_true",
        help="Run once as part of an OpenClaw heartbeat and follow the heartbeat cadence.",
    )
    parser.add_argument(
        "--auto",
        action="store_true",
        help="Deprecated alias for --heartbeat.",
    )
    parser.add_argument("--workspace", type=str, help="Workspace directory path.")
    parser.add_argument("--config", type=str, help="Path to a compression rules JSON file.")
    parser.add_argument(
        "--platform",
        type=str,
        choices=["windows", "linux", "darwin", "unix", "nt"],
        help="Override platform detection.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def _resolve_target_file(workspace_dir: Path, raw_path: str) -> Path:
    target = Path(raw_path)
    return target if target.is_absolute() else workspace_dir / target


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    workspace_dir = Path(args.workspace) if args.workspace else Path.home() / ".openclaw" / "workspace"
    if not workspace_dir.exists():
        parser.error(f"Workspace directory not found: {workspace_dir}")

    compressor = MemoryCompressor(
        workspace_dir=workspace_dir,
        config_path=Path(args.config) if args.config else None,
        platform_override=args.platform,
    )

    if args.file:
        file_paths = [_resolve_target_file(workspace_dir, args.file)]
    elif args.all or args.auto or args.heartbeat:
        file_paths = None
    else:
        parser.error("Specify --all, --file, --heartbeat, or --auto")

    try:
        results = compressor.compress_files(file_paths=file_paths, preview_only=args.preview)
    except Exception as exc:
        print(f"Error during compression: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc

    print("\n" + "=" * 60)
    print("COMPRESSION RESULTS")
    print("=" * 60)

    status = results.get("status")
    if status == "preview_only":
        print("PREVIEW MODE - No files were modified")
    elif status == "completed":
        print("COMPRESSION COMPLETED - Files have been updated")

    for file_path, stats in results.items():
        if file_path in {"backups", "status"}:
            continue
        print(f"\n{file_path}:")
        print(f"  Original size: {stats['original_size']} bytes")
        print(f"  Compressed size: {stats['compressed_size']} bytes")
        print(f"  Compression ratio: {stats['compression_ratio']:.2f}%")
        if args.preview:
            print(f"  Preview: {stats['preview_content']}")

    if args.auto or args.heartbeat:
        deleted_count = compressor.cleanup_old_backups(days_old=7)
        if deleted_count:
            print(f"\nCleaned up {deleted_count} old backup files")

    print("\n" + "=" * 60)
