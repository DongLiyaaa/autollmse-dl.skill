"""Importance scoring with file-type-aware heuristics and traceable reasons."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Optional

from .configuration import load_config
from .llm_backend import OpenAIResponsesLLMClient


class ImportanceScorer:
    """Score content blocks on a 0-10 importance scale."""

    def __init__(
        self,
        workspace_dir: Path,
        min_score_threshold: float = 5.0,
        config_path: Optional[Path] = None,
        llm_client: Optional[object] = None,
    ):
        self.workspace_dir = Path(workspace_dir)
        self.config = load_config(self.workspace_dir, config_path)
        configured_threshold = self.config.get("daily_memory", {}).get("importance_threshold")
        self.min_score_threshold = float(configured_threshold or min_score_threshold)
        self.llm_client = llm_client if llm_client is not None else OpenAIResponsesLLMClient.from_config(self.config)
        self.high_signal_keywords = {
            "critical": 2.0,
            "urgent": 1.5,
            "failed": 1.5,
            "error": 1.25,
            "decision": 1.5,
            "conclusion": 1.0,
            "summary": 0.75,
            "important": 1.25,
            "must": 1.0,
            "essential": 1.0,
            "next step": 1.5,
            "action item": 1.5,
            "todo": 1.25,
            "关键决策": 2.0,
            "重要配置": 2.0,
            "系统架构": 1.75,
            "核心身份": 1.75,
            "下一步行动": 1.75,
            "重要变量": 1.5,
            "待关注": 1.25,
            "配置": 1.0,
            "规则": 1.0,
            "策略": 1.0,
            "方案": 1.0,
        }
        self.low_signal_keywords = {
            "no_reply": -4.0,
            "heartbeat_ok": -4.0,
            "debug": -1.5,
            "test": -1.25,
            "temporary": -1.0,
            "临时": -1.0,
            "测试": -1.25,
            "调试": -1.5,
        }

    def _get_profile_name(self, file_path: str | Path) -> str:
        file_path = str(file_path)
        path = Path(file_path)
        if path.name == "MEMORY.md":
            return "MEMORY.md"
        if path.name == "HOT_MEMORY.md":
            return "hot_memory"
        if path.name == "unified_conversation_summary.md":
            return "unified_summary"
        return "daily_memory"

    def get_profile_settings(self, file_path: str | Path) -> dict:
        profile_name = self._get_profile_name(file_path)
        profile = dict(self.config.get(profile_name, {}))

        if profile_name == "MEMORY.md":
            profile.setdefault("min_importance_score", 7.0)
            profile.setdefault("soft_importance_score", 5.5)
            profile.setdefault("min_retention_ratio", 0.35)
            profile.setdefault("max_blocks", 24)
            profile.setdefault("preserve_code_blocks", True)
            profile.setdefault("keep_sections", [])
        elif profile_name == "hot_memory":
            profile.setdefault("min_importance_score", 6.0)
            profile.setdefault("soft_importance_score", 4.5)
            profile.setdefault("min_retention_ratio", 0.45)
            profile.setdefault("max_blocks", 14)
            profile.setdefault("emergency_preserve", [])
        elif profile_name == "unified_summary":
            profile.setdefault("min_importance_score", 6.0)
            profile.setdefault("soft_importance_score", 4.5)
            profile.setdefault("min_retention_ratio", 0.40)
            profile.setdefault("max_blocks", 16)
        else:
            profile.setdefault("min_importance_score", float(profile.get("importance_threshold", self.min_score_threshold)))
            profile.setdefault("soft_importance_score", 4.0)
            profile.setdefault("min_retention_ratio", 0.30)
            profile.setdefault("max_blocks", 18)

        return profile

    def _extract_header(self, text: str) -> str:
        first_line = text.strip().splitlines()[0] if text.strip() else ""
        match = re.match(r"^#{1,6}\s+(.*)$", first_line)
        return match.group(1).strip() if match else ""

    def _extract_score_from_response(self, response: str) -> float:
        match = re.search(r"\d+\.?\d*", response)
        if not match:
            return 5.0
        return max(0.0, min(10.0, float(match.group(0))))

    def _contains_date_or_path(self, content: str) -> bool:
        return bool(
            re.search(r"\b\d{4}-\d{2}-\d{2}\b", content)
            or re.search(r"\b[A-Za-z]:\\", content)
            or "/" in content
            or re.search(r"\b[a-zA-Z0-9_.-]+\.(md|py|json|toml|yaml|yml)\b", content)
        )

    def _score_block_metadata(self, content: str, profile: dict, block_type: str) -> tuple[float, list[str]]:
        lowered = content.lower()
        score = 3.5
        reasons = []

        for keyword, weight in self.high_signal_keywords.items():
            if keyword.lower() in lowered:
                score += weight
                reasons.append(f"keyword:{keyword}")

        for keyword, weight in self.low_signal_keywords.items():
            if keyword in lowered:
                score += weight
                reasons.append(f"noise:{keyword}")

        stripped = content.strip()
        char_count = len(stripped)
        line_count = len(stripped.splitlines())
        has_code_block = "```" in content
        has_list = bool(re.search(r"(^|\n)\s*([-*]|\d+\.)\s+", content))
        has_action = bool(re.search(r"\b(todo|next step|action item|follow[- ]?up)\b", lowered)) or any(
            marker in content for marker in ["待办", "下一步", "行动项", "后续"]
        )
        has_date_or_path = self._contains_date_or_path(content)

        strong_signal_hit = any(keyword.lower() in lowered for keyword in self.high_signal_keywords)

        if block_type == "section":
            score += 0.35
            reasons.append("structure:section")
        if has_code_block and profile.get("preserve_code_blocks", False):
            score += 0.75
            reasons.append("structure:code")
        if has_list:
            score += 0.4
            reasons.append("structure:list")
        if has_action:
            score += 0.85
            reasons.append("signal:actionable")
        if has_date_or_path:
            score += 0.35
            reasons.append("signal:reference")
        if 80 <= char_count <= 900:
            score += 0.75
            reasons.append("length:dense")
        elif 40 <= char_count < 80:
            score += 0.25
            reasons.append("length:compact")
        elif char_count < 20 and not strong_signal_hit:
            score -= 2.0
            reasons.append("length:too_short")
        elif char_count < 40 and not strong_signal_hit:
            score -= 1.0
            reasons.append("length:short")

        if line_count == 1 and not has_action and not has_code_block and char_count < 60 and not strong_signal_hit:
            score -= 0.75
            reasons.append("structure:thin_single_line")

        return score, reasons

    def _matches_keep_rules(self, content: str, header: str, profile: dict) -> tuple[bool, list[str]]:
        reasons = []
        keep_sections = [item for item in profile.get("keep_sections", []) if item]
        emergency_preserve = [item for item in profile.get("emergency_preserve", []) if item]

        for marker in keep_sections:
            if marker in header or marker in content:
                reasons.append(f"keep_section:{marker}")
        for marker in emergency_preserve:
            if marker in header or marker in content:
                reasons.append(f"emergency:{marker}")

        return bool(reasons), reasons

    def score_block(self, block: dict, file_path: str | Path) -> dict:
        """Return a scored copy of a block with explanations and retention priority."""
        content = block.get("text", "")
        profile = self.get_profile_settings(file_path)
        header = block.get("header") or self._extract_header(content)
        must_keep, keep_reasons = self._matches_keep_rules(content, header, profile)
        score, reasons = self._score_block_metadata(content, profile, block.get("type", "paragraph"))
        reasons.extend(keep_reasons)

        if must_keep:
            score = max(score, profile["min_importance_score"] + 1.5)

        if "NO_REPLY" in content or "HEARTBEAT_OK" in content:
            score = 0.0
            reasons.append("noise:heartbeat_marker")

        score = round(max(0.0, min(10.0, score)), 2)
        if must_keep:
            priority = "must_keep"
        elif score >= profile["min_importance_score"]:
            priority = "high"
        elif score >= profile["soft_importance_score"]:
            priority = "soft_keep"
        else:
            priority = "drop"

        scored_block = dict(block)
        scored_block["header"] = header
        scored_block["char_count"] = len(content.strip())
        scored_block["importance_score"] = score
        scored_block["importance_reasons"] = reasons
        scored_block["must_keep"] = must_keep
        scored_block["retention_priority"] = priority
        scored_block["profile_name"] = self._get_profile_name(file_path)
        return scored_block

    def _apply_llm_scores(self, file_path: str | Path, scored_blocks: list[dict]) -> list[dict]:
        if not getattr(self.llm_client, "is_enabled", lambda: False)():
            return scored_blocks

        profile = self.get_profile_settings(file_path)
        profile_name = self._get_profile_name(file_path)
        try:
            llm_scores = self.llm_client.score_blocks(
                file_path=str(file_path),
                profile_name=profile_name,
                profile=profile,
                blocks=scored_blocks,
            )
        except Exception as exc:
            print(f"Warning: LLM scoring failed for {file_path}, using heuristic scoring only: {exc}")
            return scored_blocks

        merged = []
        for block in scored_blocks:
            llm_result = llm_scores.get(str(block.get("block_id", "")))
            if not llm_result:
                merged.append(block)
                continue

            combined = dict(block)
            llm_score = max(0.0, min(10.0, float(llm_result.get("score", block["importance_score"]))))
            heuristic_score = float(block.get("importance_score", 0))
            final_score = round((heuristic_score * 0.35) + (llm_score * 0.65), 2)

            if llm_result.get("must_keep"):
                combined["must_keep"] = True
                final_score = max(final_score, float(profile["min_importance_score"]) + 1.0)

            combined["importance_score"] = min(10.0, final_score)
            if llm_result.get("reason"):
                combined.setdefault("importance_reasons", [])
                combined["importance_reasons"] = list(combined["importance_reasons"]) + [f"llm:{llm_result['reason']}"]
            if llm_result.get("summary"):
                combined["llm_summary"] = llm_result["summary"]

            if combined.get("must_keep"):
                combined["retention_priority"] = "must_keep"
            elif combined["importance_score"] >= profile["min_importance_score"]:
                combined["retention_priority"] = "high"
            elif combined["importance_score"] >= profile["soft_importance_score"]:
                combined["retention_priority"] = "soft_keep"
            else:
                combined["retention_priority"] = "drop"

            merged.append(combined)

        return merged

    def score_content_block(self, content: str, context: str = "") -> float:
        """Score a single block of content and return only the numeric score."""
        file_path = context or "memory/unknown.md"
        return self.score_block({"text": content, "type": "paragraph"}, file_path)["importance_score"]

    def filter_by_importance(self, content_blocks: list[dict], min_score: Optional[float] = None) -> list[dict]:
        """Annotate and keep blocks meeting the threshold."""
        file_path = content_blocks[0].get("source_file", "memory/unknown.md") if content_blocks else "memory/unknown.md"
        profile = self.get_profile_settings(file_path)
        threshold = profile["min_importance_score"] if min_score is None else min_score
        filtered_blocks = []

        for block in content_blocks:
            content = block.get("text", "")
            if not content.strip():
                filtered_blocks.append(block)
                continue

            scored_block = self.score_block(block, file_path)
            if scored_block["must_keep"] or scored_block["importance_score"] >= threshold:
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

    def split_content_blocks(self, content: str, file_path: str | Path) -> list[dict]:
        return _split_into_blocks(content, str(file_path))

    def score_content(self, content: str, file_path: str | Path) -> list[dict]:
        blocks = self.split_content_blocks(content, file_path)
        heuristic_blocks = [self.score_block(block, file_path) for block in blocks]
        return self._apply_llm_scores(file_path, heuristic_blocks)


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
            results[str(file_path)] = scorer.score_content(content, str(file_path))
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
                blocks.append(
                    {
                        "block_id": f"b{index}",
                        "text": section.strip(),
                        "type": "section",
                        "section_index": index,
                        "order": index,
                        "source_file": file_path,
                    }
                )
        return blocks

    paragraphs = re.split(r"\n\s*\n", content)
    for index, paragraph in enumerate(paragraphs):
        if paragraph.strip():
                blocks.append(
                    {
                        "block_id": f"b{index}",
                        "text": paragraph.strip(),
                        "type": "paragraph",
                        "order": index,
                        "source_file": file_path,
                }
            )
    return blocks
