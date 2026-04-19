"""Main compression engine for AutoLLMSE-DL."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from .backup_manager import BackupManager, create_backup_for_memory_files
from .configuration import load_config
from .importance_scoring import ImportanceScorer, score_memory_content
from .semantic_dedup import SemanticDeduplicator, deduplicate_memory_content


class MemoryCompressor:
    """Coordinate backup, deduplication, importance scoring, and safe writes."""

    def __init__(
        self,
        workspace_dir: Path,
        config_path: Optional[Path] = None,
        platform_override: Optional[str] = None,
    ):
        self.workspace_dir = Path(workspace_dir)
        self.memory_dir = self.workspace_dir / "memory"
        self.hot_memory_dir = self.memory_dir / "hot"
        self.system = (platform_override or os.name).lower()
        self.is_windows = self.system in {"windows", "nt"}
        self.config_path = Path(config_path) if config_path else None
        self.config = load_config(self.workspace_dir, self.config_path)
        self.backup_manager = BackupManager(self.workspace_dir)
        self.deduplicator = SemanticDeduplicator(self.workspace_dir)
        self.scorer = ImportanceScorer(self.workspace_dir, config_path=self.config_path)

    def _get_memory_files(self) -> list[Path]:
        memory_files = []

        memory_md = self.workspace_dir / "MEMORY.md"
        if memory_md.exists():
            memory_files.append(memory_md)

        if self.memory_dir.exists():
            for daily_file in sorted(self.memory_dir.glob("*.md")):
                if daily_file.name not in {"HOT_MEMORY.md", "unified_conversation_summary.md"}:
                    memory_files.append(daily_file)

        hot_memory = self.hot_memory_dir / "HOT_MEMORY.md"
        if hot_memory.exists():
            memory_files.append(hot_memory)

        unified_summary = self.memory_dir / "unified_conversation_summary.md"
        if unified_summary.exists():
            memory_files.append(unified_summary)

        return memory_files

    def _normalize_line_endings(self, content: str) -> str:
        return content.replace("\r\n", "\n").replace("\r", "\n")

    def _get_encoding(self) -> str:
        return "utf-8-sig" if self.is_windows else "utf-8"

    def compress_files(self, file_paths: Optional[list[Path]] = None, preview_only: bool = False) -> dict[str, dict]:
        """Compress the requested files and return summary statistics."""
        file_paths = self._get_memory_files() if file_paths is None else [Path(path) for path in file_paths]
        if not file_paths:
            print("No memory files found to compress")
            return {}

        results = {}
        if not preview_only:
            results["backups"] = create_backup_for_memory_files(file_paths, self.workspace_dir)

        original_content = {}
        encoding = self._get_encoding()
        for file_path in file_paths:
            if not file_path.exists():
                continue
            try:
                original_content[str(file_path)] = file_path.read_text(encoding=encoding)
            except Exception as exc:
                print(f"Warning: Failed to read {file_path}: {exc}")
                original_content[str(file_path)] = ""

        deduplicated_content = deduplicate_memory_content(file_paths, self.workspace_dir)
        scored_blocks = score_memory_content(file_paths, self.workspace_dir, config_path=self.config_path)

        compressed_content = {}
        for file_path_str, original in original_content.items():
            dedup_content = deduplicated_content.get(file_path_str, original)
            blocks = scored_blocks.get(file_path_str, [])

            important_content = "\n\n".join(
                block["text"]
                for block in blocks
                if block.get("importance_score", 0) >= self.scorer.min_score_threshold
            )
            selected_content = important_content.strip() or dedup_content
            compressed_content[file_path_str] = self._normalize_line_endings(selected_content)

        for file_path_str, original in original_content.items():
            compressed = compressed_content[file_path_str]
            original_size = len(original)
            compressed_size = len(compressed)
            compression_ratio = (1 - compressed_size / original_size) * 100 if original_size else 0
            results[file_path_str] = {
                "original_size": original_size,
                "compressed_size": compressed_size,
                "compression_ratio": round(compression_ratio, 2),
                "preview_content": compressed[:500] + ("..." if len(compressed) > 500 else ""),
            }

        if not preview_only:
            self._write_compressed_content(compressed_content)
            results["status"] = "completed"
        else:
            results["status"] = "preview_only"

        return results

    def _write_compressed_content(self, compressed_content: dict[str, str]) -> None:
        encoding = self._get_encoding()

        for file_path_str, content in compressed_content.items():
            file_path = Path(file_path_str)
            temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
            original_mode = file_path.stat().st_mode if file_path.exists() else None

            try:
                temp_path.parent.mkdir(parents=True, exist_ok=True)
                temp_path.write_text(content, encoding=encoding, newline="")
                temp_path.replace(file_path)

                if original_mode is not None and not self.is_windows:
                    os.chmod(file_path, original_mode)
            except Exception:
                if temp_path.exists():
                    temp_path.unlink()
                raise

    def cleanup_old_backups(self, days_old: int = 30) -> int:
        return self.backup_manager.cleanup_old_backups(days_old)
