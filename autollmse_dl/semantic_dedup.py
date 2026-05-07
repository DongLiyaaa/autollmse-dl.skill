"""Semantic deduplication with optional embedding support."""

from __future__ import annotations

import hashlib
import os
from difflib import SequenceMatcher
from pathlib import Path

from .configuration import load_config

try:
    import numpy as np
except ImportError:  # pragma: no cover - exercised through fallback paths
    np = None

try:
    from sentence_transformers import SentenceTransformer
except ImportError:  # pragma: no cover - exercised through fallback paths
    SentenceTransformer = None


class SemanticDeduplicator:
    """Deduplicate content blocks while gracefully handling missing ML dependencies."""

    def __init__(self, workspace_dir: Path, similarity_threshold: float = 0.85):
        self.workspace_dir = Path(workspace_dir)
        self.similarity_threshold = similarity_threshold
        self.config = load_config(self.workspace_dir)
        self.model = None
        self.model_settings = self._load_model_settings()
        self.cache_dir = self.workspace_dir / ".cache" / "embeddings"
        configured_model_cache_dir = Path(self.model_settings["cache_dir"])
        self.model_cache_dir = (
            configured_model_cache_dir
            if configured_model_cache_dir.is_absolute()
            else self.workspace_dir / configured_model_cache_dir
        )
        self._load_embedding_model()
        if self.model is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self.model_cache_dir.mkdir(parents=True, exist_ok=True)

    def _env_bool(self, name: str, default: bool) -> bool:
        raw = os.getenv(name)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def _load_model_settings(self) -> dict:
        config = dict(self.config.get("semantic_model", {}))
        default_cache_dir = self.workspace_dir / ".cache" / "models"
        return {
            "provider": os.getenv("AUTOLLMSE_DL_EMBEDDING_PROVIDER", config.get("provider", "sentence_transformers")),
            "model_name": os.getenv("AUTOLLMSE_DL_EMBEDDING_MODEL", config.get("model_name", "BAAI/bge-m3")),
            "auto_download": self._env_bool(
                "AUTOLLMSE_DL_EMBEDDING_AUTO_DOWNLOAD",
                bool(config.get("auto_download", True)),
            ),
            "local_files_only": self._env_bool(
                "AUTOLLMSE_DL_EMBEDDING_LOCAL_ONLY",
                bool(config.get("local_files_only", False)),
            ),
            "cache_dir": os.getenv("AUTOLLMSE_DL_EMBEDDING_CACHE_DIR", str(config.get("cache_dir", default_cache_dir))),
        }

    def _load_embedding_model(self) -> None:
        if SentenceTransformer is None or np is None:
            return
        if self.model_settings["provider"] != "sentence_transformers":
            return

        model_name = self.model_settings["model_name"]
        auto_download = self.model_settings["auto_download"]
        local_files_only = self.model_settings["local_files_only"] or not auto_download

        try:
            self.model = SentenceTransformer(
                model_name,
                cache_folder=str(self.model_cache_dir),
                local_files_only=local_files_only,
            )
        except Exception as exc:
            mode = "local-only" if local_files_only else "auto-download"
            print(
                f"Warning: Failed to load embedding model {model_name} "
                f"(mode={mode}), falling back to text matching: {exc}"
            )
            self.model = None

    def _get_cache_path(self, content_hash: str) -> Path:
        return self.cache_dir / f"{content_hash}.npy"

    def _compute_embedding(self, text: str):
        if self.model is None or np is None:
            return None

        content_hash = hashlib.md5(text.encode("utf-8")).hexdigest()
        cache_path = self._get_cache_path(content_hash)

        if cache_path.exists():
            try:
                return np.load(cache_path)
            except Exception:
                pass

        try:
            embedding = self.model.encode([text], convert_to_numpy=True)[0]
            np.save(cache_path, embedding)
            return embedding
        except Exception as exc:
            print(f"Warning: Failed to compute embedding, falling back to text matching: {exc}")
            return None

    def _cosine_similarity(self, emb1, emb2) -> float:
        return float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2)))

    def _fallback_similarity(self, text1: str, text2: str) -> float:
        normalized_a = " ".join(text1.lower().split())
        normalized_b = " ".join(text2.lower().split())
        return SequenceMatcher(None, normalized_a, normalized_b).ratio()

    def _is_similar(self, text1: str, text2: str) -> bool:
        if self.model is None or np is None:
            return self._fallback_similarity(text1, text2) >= self.similarity_threshold

        emb1 = self._compute_embedding(text1)
        emb2 = self._compute_embedding(text2)
        if emb1 is None or emb2 is None:
            return self._fallback_similarity(text1, text2) >= self.similarity_threshold
        return self._cosine_similarity(emb1, emb2) >= self.similarity_threshold

    def remove_duplicates(self, content_blocks: list[dict]) -> list[dict]:
        """Remove duplicate or near-duplicate blocks while preserving order."""
        deduplicated = []
        processed_texts = []

        for block in content_blocks:
            current_text = block.get("text", "").strip()
            if not current_text:
                deduplicated.append(block)
                continue

            if any(self._is_similar(current_text, processed_text) for processed_text in processed_texts):
                continue

            deduplicated.append(block)
            processed_texts.append(current_text)

        return deduplicated

    def deduplicate_file_content(self, file_content: str, chunk_size: int = 1000) -> str:
        """Deduplicate a file by chunking it into paragraph-like blocks."""
        if not file_content.strip():
            return file_content

        lines = file_content.split("\n")
        chunks = []
        current_chunk = []

        for line in lines:
            current_chunk.append(line)
            if len("\n".join(current_chunk)) >= chunk_size or line.strip() == "":
                chunk = "\n".join(current_chunk).strip()
                if chunk:
                    chunks.append(chunk)
                current_chunk = []

        final_chunk = "\n".join(current_chunk).strip()
        if final_chunk:
            chunks.append(final_chunk)

        blocks = [{"text": chunk} for chunk in chunks]
        return "\n\n".join(block["text"] for block in self.remove_duplicates(blocks))

    def clear_cache(self) -> None:
        """Remove cached embeddings."""
        if self.cache_dir.exists():
            for file_path in self.cache_dir.glob("*.npy"):
                file_path.unlink()


def deduplicate_memory_content(memory_files: list[Path], workspace_dir: Path) -> dict[str, str]:
    """Deduplicate content across memory files."""
    deduplicator = SemanticDeduplicator(workspace_dir)
    results = {}

    for file_path in memory_files:
        file_path = Path(file_path)
        if not file_path.exists():
            continue
        try:
            encoding = "utf-8-sig" if os.name == "nt" else "utf-8"
            content = file_path.read_text(encoding=encoding)
            results[str(file_path)] = deduplicator.deduplicate_file_content(content)
        except Exception as exc:
            print(f"Warning: Failed to deduplicate {file_path}: {exc}")
            try:
                results[str(file_path)] = file_path.read_text(encoding="utf-8")
            except Exception:
                results[str(file_path)] = ""

    return results
