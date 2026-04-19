"""
Cross-platform semantic deduplication module for AutoLLMSE-DL skill.
Uses BAAI/bge-m3 embeddings to identify and remove semantically similar content.
Compatible with Windows, Linux, and macOS.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
import platform


class SemanticDeduplicator:
    """Handles semantic deduplication of text content using embeddings."""
    
    def __init__(self, workspace_dir: Path, similarity_threshold: float = 0.85):
        self.workspace_dir = Path(workspace_dir)
        self.similarity_threshold = similarity_threshold
        self.system = platform.system().lower()
        
        # Initialize embedding model
        self.model = None
        self._load_embedding_model()
        
        # Cache directory for embeddings
        self.cache_dir = self.workspace_dir / ".cache" / "embeddings"
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    
    def _load_embedding_model(self):
        """Load the BAAI/bge-m3 embedding model."""
        try:
            # Use the same model as configured in TOOLS.md
            self.model = SentenceTransformer('BAAI/bge-m3')
        except Exception as e:
            print(f"Warning: Failed to load BAAI/bge-m3 model: {e}")
            print("Falling back to simple text-based deduplication")
            self.model = None
    
    def _get_cache_path(self, content_hash: str) -> Path:
        """Get cache file path for a given content hash."""
        return self.cache_dir / f"{content_hash}.npy"
    
    def _compute_embedding(self, text: str) -> Optional[np.ndarray]:
        """Compute embedding for text, using cache if available."""
        if self.model is None:
            return None
            
        # Create content hash
        import hashlib
        content_hash = hashlib.md5(text.encode('utf-8')).hexdigest()
        cache_path = self._get_cache_path(content_hash)
        
        # Check cache first
        if cache_path.exists():
            try:
                return np.load(cache_path)
            except Exception:
                pass
        
        # Compute embedding
        try:
            embedding = self.model.encode([text], convert_to_numpy=True)[0]
            # Save to cache
            np.save(cache_path, embedding)
            return embedding
        except Exception as e:
            print(f"Warning: Failed to compute embedding: {e}")
            return None
    
    def _cosine_similarity(self, emb1: np.ndarray, emb2: np.ndarray) -> float:
        """Compute cosine similarity between two embeddings."""
        return float(np.dot(emb1, emb2) / (np.linalg.norm(emb1) * np.linalg.norm(emb2)))
    
    def _is_similar(self, text1: str, text2: str) -> bool:
        """Check if two texts are semantically similar."""
        if self.model is None:
            # Fallback to simple text comparison
            return text1.strip() == text2.strip()
        
        emb1 = self._compute_embedding(text1)
        emb2 = self._compute_embedding(text2)
        
        if emb1 is None or emb2 is None:
            return False
        
        similarity = self._cosine_similarity(emb1, emb2)
        return similarity >= self.similarity_threshold
    
    def remove_duplicates(self, content_blocks: List[Dict]) -> List[Dict]:
        """
        Remove semantically duplicate content blocks.
        Each block should be a dict with 'text' key and other metadata.
        Returns deduplicated list preserving order.
        """
        if not content_blocks:
            return []
        
        deduplicated = []
        processed_texts = []
        
        for block in content_blocks:
            current_text = block.get('text', '').strip()
            if not current_text:
                deduplicated.append(block)
                continue
            
            # Check against all previously processed texts
            is_duplicate = False
            for processed_text in processed_texts:
                if self._is_similar(current_text, processed_text):
                    is_duplicate = True
                    break
            
            if not is_duplicate:
                deduplicated.append(block)
                processed_texts.append(current_text)
        
        return deduplicated
    
    def deduplicate_file_content(self, file_content: str, chunk_size: int = 1000) -> str:
        """
        Deduplicate content within a single file by splitting into chunks.
        Returns deduplicated content.
        """
        if not file_content.strip():
            return file_content
        
        # Split content into reasonable chunks (paragraphs or sections)
        lines = file_content.split('\n')
        chunks = []
        current_chunk = []
        
        for line in lines:
            current_chunk.append(line)
            if len('\n'.join(current_chunk)) >= chunk_size or line.strip() == '':
                if current_chunk:
                    chunks.append('\n'.join(current_chunk))
                    current_chunk = []
        
        # Add remaining content
        if current_chunk:
            chunks.append('\n'.join(current_chunk))
        
        # Create content blocks
        content_blocks = [{'text': chunk, 'original': chunk} for chunk in chunks if chunk.strip()]
        
        # Deduplicate
        deduplicated_blocks = self.remove_duplicates(content_blocks)
        
        # Reconstruct content
        deduplicated_content = '\n'.join([block['text'] for block in deduplicated_blocks])
        return deduplicated_content
    
    def clear_cache(self):
        """Clear the embedding cache."""
        import shutil
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)
            self.cache_dir.mkdir(parents=True, exist_ok=True)


def deduplicate_memory_content(memory_files: List[Path], workspace_dir: Path) -> Dict[str, str]:
    """
    Deduplicate content across multiple memory files.
    Returns dictionary mapping file paths to deduplicated content.
    """
    deduplicator = SemanticDeduplicator(workspace_dir)
    results = {}
    
    for file_path in memory_files:
        if not file_path.exists():
            continue
            
        try:
            # Read file content with proper encoding
            encoding = 'utf-8-sig' if platform.system().lower() == 'windows' else 'utf-8'
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            
            # Deduplicate content
            deduplicated_content = deduplicator.deduplicate_file_content(content)
            results[str(file_path)] = deduplicated_content
            
        except Exception as e:
            print(f"Warning: Failed to deduplicate {file_path}: {e}")
            # Return original content on failure
            try:
                encoding = 'utf-8-sig' if platform.system().lower() == 'windows' else 'utf-8'
                with open(file_path, 'r', encoding=encoding) as f:
                    results[str(file_path)] = f.read()
            except Exception:
                results[str(file_path)] = ""
    
    return results


if __name__ == "__main__":
    # Example usage
    workspace = Path.home() / ".openclaw" / "workspace"
    memory_files = [
        workspace / "MEMORY.md",
        workspace / "memory" / "2026-04-20.md"
    ]
    
    results = deduplicate_memory_content(memory_files, workspace)
    for file_path, content in results.items():
        print(f"Deduplicated {file_path}, length: {len(content)}")