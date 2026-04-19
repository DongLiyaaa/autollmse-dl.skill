"""Semantic deduplication with optional embedding support."""

from __future__ import annotations

import hashlib
import os
from difflib import SequenceMatcher
from pathlib import Path

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
        self.model = None
        self.cache_dir = self.workspace_dir / ".cache" / "embeddings"
        self._load_embedding_model()
        if self.model is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _load_embedding_model(self) -> None:
        if SentenceTransformer is None or np is None:
            return
        try:
            self.model = SentenceTransformer("BAAI/bge-m3")
        except Exception as exc:
            print(f"Warning: Failed to load BAAI/bge-m3 model, falling back to text matching: {exc}")
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
