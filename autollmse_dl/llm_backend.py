"""Optional real LLM backend for semantic scoring and summary generation."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional


class OpenAIResponsesLLMClient:
    """Small OpenAI Responses API client using the standard library only."""

    def __init__(
        self,
        *,
        enabled: bool,
        api_key: Optional[str],
        model: str,
        timeout_seconds: int = 45,
        max_block_chars: int = 1200,
        api_base: str = "https://api.openai.com/v1",
    ):
        self.enabled = enabled and bool(api_key)
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_block_chars = max_block_chars
        self.api_base = api_base.rstrip("/")

    @classmethod
    def from_config(cls, config: dict) -> "OpenAIResponsesLLMClient":
        llm_config = dict(config.get("llm", {}))
        provider = os.getenv("AUTOLLMSE_DL_LLM_PROVIDER", llm_config.get("provider", "openai")).lower()
        enabled = os.getenv("AUTOLLMSE_DL_LLM_ENABLED", str(llm_config.get("enabled", False))).lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
        api_key = os.getenv("OPENAI_API_KEY") or llm_config.get("api_key")
        model = os.getenv("AUTOLLMSE_DL_OPENAI_MODEL", llm_config.get("model", "gpt-4o-mini"))
        timeout_seconds = int(os.getenv("AUTOLLMSE_DL_LLM_TIMEOUT", llm_config.get("timeout_seconds", 45)))
        max_block_chars = int(os.getenv("AUTOLLMSE_DL_LLM_MAX_BLOCK_CHARS", llm_config.get("max_block_chars", 1200)))
        api_base = os.getenv("OPENAI_BASE_URL", llm_config.get("api_base", "https://api.openai.com/v1"))

        if provider != "openai":
            enabled = False

        return cls(
            enabled=enabled,
            api_key=api_key,
            model=model,
            timeout_seconds=timeout_seconds,
            max_block_chars=max_block_chars,
            api_base=api_base,
        )

    def is_enabled(self) -> bool:
        return self.enabled

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, int) and value in {0, 1}:
            return bool(value)
        return False

    def score_blocks(self, *, file_path: str, profile_name: str, profile: dict, blocks: list[dict]) -> dict[str, dict]:
        """Return LLM scores keyed by block_id."""
        if not self.is_enabled() or not blocks:
            return {}

        payload_blocks = []
        for block in blocks:
            payload_blocks.append(
                {
                    "block_id": block.get("block_id"),
                    "header": block.get("header", ""),
                    "type": block.get("type", "paragraph"),
                    "heuristic_score": block.get("importance_score"),
                    "heuristic_priority": block.get("retention_priority"),
                    "must_keep_hint": block.get("must_keep", False),
                    "text": block.get("text", "")[: self.max_block_chars],
                }
            )

        system_prompt = (
            "You are ranking Markdown memory blocks for compression. "
            "Return JSON only. Score each block from 0 to 10. "
            "Prefer preserving decisions, configurations, architecture, next steps, action items, and concrete references. "
            "Penalize noise, transient debug chatter, and trivial status markers. "
            "Generate a short summary sentence for each retained-worthy block."
        )
        user_payload = {
            "task": "Score memory blocks for retention during compression and produce concise summaries.",
            "output_requirements": {
                "format": "JSON",
                "top_level_key": "blocks",
                "fields": ["block_id", "score", "must_keep", "summary", "reason"],
            },
            "file_path": file_path,
            "profile_name": profile_name,
            "profile": {
                "min_importance_score": profile.get("min_importance_score"),
                "soft_importance_score": profile.get("soft_importance_score"),
                "keep_sections": profile.get("keep_sections", []),
                "emergency_preserve": profile.get("emergency_preserve", []),
                "preserve_code_blocks": profile.get("preserve_code_blocks", False),
            },
            "blocks": payload_blocks,
        }

        response_json = self._responses_json(system_prompt, json.dumps(user_payload, ensure_ascii=False))
        raw_blocks = response_json.get("blocks", [])
        results = {}
        for item in raw_blocks:
            block_id = str(item.get("block_id", "")).strip()
            if not block_id:
                continue
            try:
                score = float(item.get("score", 0))
            except (TypeError, ValueError):
                score = 0.0
            results[block_id] = {
                "score": max(0.0, min(10.0, score)),
                "must_keep": self._coerce_bool(item.get("must_keep", False)),
                "summary": str(item.get("summary", "")).strip(),
                "reason": str(item.get("reason", "")).strip(),
            }
        return results

    def _responses_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "text": {"format": {"type": "json_object"}},
        }
        request = urllib.request.Request(
            f"{self.api_base}/responses",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"OpenAI Responses API error: HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"OpenAI Responses API request failed: {exc.reason}") from exc

        payload = json.loads(body)
        text = self._extract_output_text(payload)
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise RuntimeError("OpenAI Responses API returned non-JSON content") from exc

    def _extract_output_text(self, payload: dict[str, Any]) -> str:
        texts = []
        for item in payload.get("output", []):
            if item.get("type") != "message":
                continue
            for content in item.get("content", []):
                if content.get("type") == "output_text":
                    texts.append(content.get("text", ""))
                elif content.get("type") == "refusal":
                    raise RuntimeError(f"OpenAI model refusal: {content.get('refusal', '')}")

        text = "".join(texts).strip()
        if text:
            return text
        raise RuntimeError("OpenAI Responses API returned no output_text content")
