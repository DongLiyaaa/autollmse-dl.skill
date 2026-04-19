"""Importance scoring with lightweight heuristic fallback."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional

from .configuration import load_config


class ImportanceScorer:
    """Score content blocks on a 0-10 importance scale."""

    def __init__(self, workspace_dir: Path, min_score_threshold: float = 5.0, config_path: Optional[Path] = None):
        self.workspace_dir = Path(workspace_dir)
        self.config = load_config(self.workspace_dir, config_path)
        configured_threshold = self.config.get("daily_memory", {}).get("importance_threshold")
        self.min_score_threshold = float(configured_threshold or min_score_threshold)

    def _get_local_llm_response(self, prompt: str) -> str:
        """Placeholder hook for a local LLM integration."""
        score = 5.0

        if any(keyword in prompt.lower() for keyword in ["核心身份", "重要配置", "关键决策", "系统架构"]):
            score += 3.0
        if any(keyword in prompt.lower() for keyword in ["error", "failed", "critical", "urgent"]):
            score += 2.0
        if any(keyword in prompt.lower() for keyword in ["decision", "conclusion", "summary"]):
            score += 1.5
        if len(prompt.strip()) < 50:
            score -= 1.0
        if prompt.strip().startswith(("NO_REPLY", "HEARTBEAT_OK")):
            score = 0.0

        return str(round(max(0.0, min(10.0, score)), 1))

    def _extract_score_from_response(self, response: str) -> float:
        match = re.search(r"\d+\.?\d*", response)
        if not match:
            return 5.0
        return max(0.0, min(10.0, float(match.group(0))))

    def score_content_block(self, content: str, context: str = "") -> float:
        """Score a single block of content."""
        del context
        if not content.strip():
            return 0.0

        prompt = f"""
Rate the importance of the following content on a scale of 0-10.

Content to score:
{content[:1000]}
"""
        try:
            return self._extract_score_from_response(self._get_local_llm_response(prompt))
        except Exception as exc:
            print(f"Warning: Failed to score content, using fallback scoring: {exc}")
            return self._fallback_scoring(content)

    def _fallback_scoring(self, content: str) -> float:
        """Score content without an LLM dependency."""
        lowered = content.lower()
        high_indicators = [
            "核心身份",
            "重要配置",
            "关键决策",
            "系统架构",
            "待关注",
            "decision",
            "critical",
            "important",
            "must",
            "essential",
            "配置",
            "设置",
            "规则",
            "策略",
            "方案",
        ]
        low_indicators = ["no_reply", "heartbeat_ok", "debug", "test", "temporary", "临时", "测试", "调试"]

        score = 5.0
        if any(indicator in lowered for indicator in high_indicators):
            score += 3.0
        if any(indicator in lowered for indicator in low_indicators):
            score -= 3.0
        if len(content) > 200:
            score += 1.0
        elif len(content) < 50:
            score -= 1.0

        return max(0.0, min(10.0, score))

    def filter_by_importance(self, content_blocks: list[dict], min_score: Optional[float] = None) -> list[dict]:
        """Annotate and keep blocks meeting the threshold."""
        threshold = self.min_score_threshold if min_score is None else min_score
        filtered_blocks = []

        for block in content_blocks:
            content = block.get("text", "")
            if not content.strip():
                filtered_blocks.append(block)
                continue

            score = self.score_content_block(content)
            scored_block = dict(block)
            scored_block["importance_score"] = score
            if score >= threshold:
                filtered_blocks.append(scored_block)

        return filtered_blocks

    def apply_time_decay(self, content_blocks: list[dict], decay_factor: float = 0.8) -> list[dict]:
        """Apply time-based decay to importance scores in place."""
        current_time = time.time()

        for block in content_blocks:
            if "timestamp" not in block or "importance_score" not in block:
                continue
            try:
                block_time = float(block["timestamp"])
            except (TypeError, ValueError):
                continue
            time_diff_days = (current_time - block_time) / (24 * 3600)
            block["importance_score"] *= decay_factor ** time_diff_days

        return content_blocks


def score_memory_content(memory_files: list[Path], workspace_dir: Path, config_path: Optional[Path] = None) -> dict[str, list[dict]]:
    """Score content blocks across multiple memory files."""
    scorer = ImportanceScorer(workspace_dir, config_path=config_path)
    results = {}

    for file_path in memory_files:
        file_path = Path(file_path)
        if not file_path.exists():
            continue
        try:
            encoding = "utf-8-sig" if os.name == "nt" else "utf-8"
            content = file_path.read_text(encoding=encoding)
            blocks = _split_into_blocks(content, str(file_path))
            results[str(file_path)] = scorer.filter_by_importance(blocks)
        except Exception as exc:
            print(f"Warning: Failed to score {file_path}: {exc}")
            results[str(file_path)] = []

    return results


def _split_into_blocks(content: str, file_path: str) -> list[dict]:
    """Split content into sections or paragraphs."""
    blocks = []
    if file_path.endswith("MEMORY.md"):
        sections = re.split(r"\n(?=#{1,6}\s)", content)
        for index, section in enumerate(sections):
            if section.strip():
                blocks.append({"text": section.strip(), "type": "section", "section_index": index})
        return blocks

    paragraphs = re.split(r"\n\s*\n", content)
    for paragraph in paragraphs:
        if paragraph.strip():
            blocks.append({"text": paragraph.strip(), "type": "paragraph"})
    return blocks
