"""Main compression engine for AutoLLMSE-DL."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from .backup_manager import BackupManager, create_backup_for_memory_files
from .configuration import load_config
from .importance_scoring import ImportanceScorer
from .semantic_dedup import SemanticDeduplicator, deduplicate_memory_content


class MemoryCompressor:
    """Coordinate backup, deduplication, importance scoring, and safe writes."""

    def __init__(
        self,
        workspace_dir: Path,
        config_path: Optional[Path] = None,
        platform_override: Optional[str] = None,
        llm_client: Optional[object] = None,
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
        self.scorer = ImportanceScorer(self.workspace_dir, config_path=self.config_path, llm_client=llm_client)

    def _get_profile_settings(self, file_path: str | Path) -> dict:
        return self.scorer.get_profile_settings(file_path)

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

    def _extract_block_summary_line(self, block: dict) -> str:
        text = block.get("text", "").strip()
        if not text:
            return ""

        header = block.get("header", "").strip()
        llm_summary = block.get("llm_summary", "").strip()
        body_lines = [line.strip() for line in text.splitlines() if line.strip()]
        if header:
            body_lines = [line for line in body_lines if line != f"# {header}" and not re.match(r"^#{1,6}\s+", line)]
            snippet = llm_summary or (body_lines[0] if body_lines else header)
            return f"- {header}: {snippet[:120]}".rstrip(": ").strip()

        snippet = llm_summary or (body_lines[0] if body_lines else text)
        return f"- {snippet[:140]}"

    def _build_summary_header(self, file_path: str, selected_blocks: list[dict], source_length: int) -> str:
        profile = self._get_profile_settings(file_path)

        top_blocks = sorted(
            selected_blocks,
            key=lambda block: (
                0 if block.get("must_keep") else 1,
                -block.get("importance_score", 0),
                block.get("order", 0),
            ),
        )[: min(3, len(selected_blocks))]

        summary_lines = [self._extract_block_summary_line(block) for block in top_blocks]
        summary_lines = [line for line in summary_lines if line]
        if not summary_lines:
            return ""

        profile_label = self.scorer._get_profile_name(file_path)
        header_lines = [
            "<!-- autollmse-dl:summary -->",
            "## Compression Summary",
            f"- Profile: {profile_label}",
            f"- Source size: {source_length} chars",
            f"- Retained blocks: {len(selected_blocks)} / {profile.get('max_blocks', len(selected_blocks))}",
            "- Key retained points:",
            *summary_lines,
        ]
        return "\n".join(header_lines).strip()

    def _rebuild_compressed_content(self, file_path: str, dedup_content: str, scored_blocks: list[dict]) -> str:
        profile = self._get_profile_settings(file_path)
        if not dedup_content.strip():
            return dedup_content
        if not scored_blocks:
            return dedup_content

        target_chars = max(120, int(len(dedup_content) * float(profile.get("min_retention_ratio", 0.3))))
        max_blocks = int(profile.get("max_blocks", 18))
        min_score = float(profile.get("min_importance_score", self.scorer.min_score_threshold))
        soft_score = float(profile.get("soft_importance_score", max(min_score - 1.0, 0.0)))

        must_keep = [block for block in scored_blocks if block.get("must_keep")]
        high = [block for block in scored_blocks if not block.get("must_keep") and block.get("importance_score", 0) >= min_score]
        soft = [
            block
            for block in scored_blocks
            if not block.get("must_keep") and soft_score <= block.get("importance_score", 0) < min_score
        ]

        selected = []
        seen_texts = set()

        def append_blocks(blocks: list[dict]) -> None:
            for block in blocks:
                text = block.get("text", "").strip()
                if not text or text in seen_texts:
                    continue
                selected.append(block)
                seen_texts.add(text)

        append_blocks(sorted(must_keep, key=lambda block: block.get("order", 0)))
        append_blocks(sorted(high, key=lambda block: (-block.get("importance_score", 0), block.get("order", 0))))

        selected_chars = sum(len(block["text"].strip()) for block in selected)
        if selected_chars < target_chars or len(selected) < min(3, max_blocks):
            append_blocks(sorted(soft, key=lambda block: (-block.get("importance_score", 0), block.get("order", 0))))

        selected = sorted(selected, key=lambda block: block.get("order", 0))

        trimmed = []
        retained_chars = 0
        for block in selected:
            if len(trimmed) >= max_blocks:
                break
            trimmed.append(block)
            retained_chars += len(block["text"].strip())
            if retained_chars >= target_chars and block.get("retention_priority") != "must_keep":
                break

        if not trimmed:
            return dedup_content

        rebuilt_body = "\n\n".join(block["text"].strip() for block in trimmed if block.get("text", "").strip())
        summary_header = self._build_summary_header(file_path, trimmed, len(dedup_content))
        rebuilt_content = f"{summary_header}\n\n{rebuilt_body}".strip() if summary_header else rebuilt_body
        if len(rebuilt_content.strip()) < max(80, int(len(dedup_content) * 0.15)):
            return dedup_content
        return rebuilt_content

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
        scored_blocks = {}
        for file_path_str, dedup_content in deduplicated_content.items():
            scored_blocks[file_path_str] = self.scorer.score_content(dedup_content, file_path_str)

        compressed_content = {}
        for file_path_str, original in original_content.items():
            dedup_content = deduplicated_content.get(file_path_str, original)
            blocks = scored_blocks.get(file_path_str, [])
            selected_content = self._rebuild_compressed_content(file_path_str, dedup_content, blocks)
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
