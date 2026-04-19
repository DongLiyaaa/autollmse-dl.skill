"""
Cross-platform importance scoring module for AutoLLMSE-DL skill.
Uses local LLM to score the importance of content blocks on a 0-10 scale.
Compatible with Windows, Linux, and macOS.
"""

import os
import re
from pathlib import Path
from typing import List, Dict, Tuple, Optional
import platform


class ImportanceScorer:
    """Scores the importance of text content using local LLM."""
    
    def __init__(self, workspace_dir: Path, min_score_threshold: float = 5.0):
        self.workspace_dir = Path(workspace_dir)
        self.min_score_threshold = min_score_threshold
        self.system = platform.system().lower()
        
        # Load configuration
        self.config_path = self.workspace_dir / "skills" / "autollmse-dl" / "config" / "compression_rules.json"
        self.config = self._load_config()
    
    def _load_config(self) -> dict:
        """Load compression configuration."""
        try:
            if self.config_path.exists():
                import json
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {}
        except Exception as e:
            print(f"Warning: Failed to load config: {e}")
            return {}
    
    def _get_local_llm_response(self, prompt: str) -> str:
        """
        Get response from local LLM.
        This is a placeholder - in practice, this would interface with ollama or similar.
        """
        # For now, use simple heuristic-based scoring
        # In real implementation, this would call the local LLM
        
        # Simple heuristics for importance scoring
        score = 5.0  # base score
        
        # Increase score for key indicators
        if any(keyword in prompt.lower() for keyword in ['核心身份', '重要配置', '关键决策', '系统架构']):
            score += 3.0
        if any(keyword in prompt.lower() for keyword in ['error', 'failed', 'critical', 'urgent']):
            score += 2.0
        if any(keyword in prompt.lower() for keyword in ['decision', 'conclusion', 'summary']):
            score += 1.5
        
        # Decrease score for low-value content
        if len(prompt.strip()) < 50:
            score -= 1.0
        if prompt.strip().startswith(('NO_REPLY', 'HEARTBEAT_OK')):
            score = 0.0
        
        # Clamp to 0-10 range
        score = max(0.0, min(10.0, score))
        
        return str(round(score, 1))
    
    def _extract_score_from_response(self, response: str) -> float:
        """Extract numerical score from LLM response."""
        # Look for numbers in the response
        numbers = re.findall(r'\d+\.?\d*', response)
        if numbers:
            try:
                score = float(numbers[0])
                return max(0.0, min(10.0, score))
            except ValueError:
                pass
        
        # Default fallback
        return 5.0
    
    def score_content_block(self, content: str, context: str = "") -> float:
        """
        Score the importance of a content block.
        Returns a score between 0-10.
        """
        if not content.strip():
            return 0.0
        
        # Create prompt for LLM
        prompt = f"""
Rate the importance of the following content on a scale of 0-10, where:
- 0-3: Low importance (can be safely removed)
- 4-6: Medium importance (keep if space allows)  
- 7-10: High importance (must preserve)

Consider these factors:
- Contains critical decisions or configurations
- Includes unique insights or lessons learned
- References specific dates, people, or events
- Provides actionable information
- Is part of structured documentation

Content to score:
{content[:1000]}  # Limit to first 1000 chars for efficiency

Respond with only a single number between 0 and 10.
"""
        
        try:
            llm_response = self._get_local_llm_response(prompt)
            score = self._extract_score_from_response(llm_response)
            return score
        except Exception as e:
            print(f"Warning: Failed to score content, using default: {e}")
            # Fallback heuristic scoring
            return self._fallback_scoring(content)
    
    def _fallback_scoring(self, content: str) -> float:
        """Fallback scoring when LLM is unavailable."""
        content_lower = content.lower()
        
        # High importance indicators
        high_indicators = [
            '核心身份', '重要配置', '关键决策', '系统架构', '待关注',
            'decision', 'critical', 'important', 'must', 'essential',
            '配置', '设置', '规则', '策略', '方案'
        ]
        
        # Low importance indicators  
        low_indicators = [
            'NO_REPLY', 'HEARTBEAT_OK', 'debug', 'test', 'temporary',
            '临时', '测试', '调试'
        ]
        
        score = 5.0
        
        if any(indicator in content_lower for indicator in high_indicators):
            score += 3.0
        if any(indicator in content_lower for indicator in low_indicators):
            score -= 3.0
        
        # Length factor
        if len(content) > 200:
            score += 1.0
        elif len(content) < 50:
            score -= 1.0
        
        return max(0.0, min(10.0, score))
    
    def filter_by_importance(self, content_blocks: List[Dict], 
                           min_score: Optional[float] = None) -> List[Dict]:
        """
        Filter content blocks by importance score.
        Returns blocks with score >= min_score.
        """
        if min_score is None:
            min_score = self.min_score_threshold
            
        filtered_blocks = []
        
        for block in content_blocks:
            content = block.get('text', '')
            if not content.strip():
                filtered_blocks.append(block)
                continue
                
            score = self.score_content_block(content)
            block['importance_score'] = score
            
            if score >= min_score:
                filtered_blocks.append(block)
        
        return filtered_blocks
    
    def apply_time_decay(self, content_blocks: List[Dict], 
                        decay_factor: float = 0.8) -> List[Dict]:
        """
        Apply time-based decay to importance scores.
        Assumes blocks have 'timestamp' field.
        """
        import time
        current_time = time.time()
        
        for block in content_blocks:
            if 'timestamp' in block and 'importance_score' in block:
                try:
                    block_time = float(block['timestamp'])
                    time_diff_days = (current_time - block_time) / (24 * 3600)
                    decay_multiplier = decay_factor ** time_diff_days
                    block['importance_score'] *= decay_multiplier
                except (ValueError, TypeError):
                    pass  # Skip if timestamp is invalid
        
        return content_blocks


def score_memory_content(memory_files: List[Path], workspace_dir: Path) -> Dict[str, List[Dict]]:
    """
    Score importance of content across multiple memory files.
    Returns dictionary mapping file paths to scored content blocks.
    """
    scorer = ImportanceScorer(workspace_dir)
    results = {}
    
    for file_path in memory_files:
        if not file_path.exists():
            continue
            
        try:
            # Read file content
            encoding = 'utf-8-sig' if platform.system().lower() == 'windows' else 'utf-8'
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
            
            # Split into logical blocks (sections, paragraphs)
            blocks = _split_into_blocks(content, str(file_path))
            
            # Score blocks
            scored_blocks = scorer.filter_by_importance(blocks)
            results[str(file_path)] = scored_blocks
            
        except Exception as e:
            print(f"Warning: Failed to score {file_path}: {e}")
            results[str(file_path)] = []
    
    return results


def _split_into_blocks(content: str, file_path: str) -> List[Dict]:
    """Split content into logical blocks for scoring."""
    blocks = []
    
    # Handle MEMORY.md specially (section-based)
    if 'MEMORY.md' in file_path:
        # Split by markdown headers
        sections = re.split(r'\n#+\s+', content)
        for i, section in enumerate(sections):
            if section.strip():
                blocks.append({
                    'text': section.strip(),
                    'type': 'section',
                    'section_index': i
                })
    else:
        # Split by paragraphs (double newlines)
        paragraphs = re.split(r'\n\s*\n', content)
        for para in paragraphs:
            if para.strip():
                blocks.append({
                    'text': para.strip(),
                    'type': 'paragraph'
                })
    
    return blocks


if __name__ == "__main__":
    # Example usage
    workspace = Path.home() / ".openclaw" / "workspace"
    memory_files = [
        workspace / "MEMORY.md",
        workspace / "memory" / "2026-04-20.md"
    ]
    
    results = score_memory_content(memory_files, workspace)
    for file_path, blocks in results.items():
        avg_score = sum(b.get('importance_score', 0) for b in blocks) / len(blocks) if blocks else 0
        print(f"Scored {file_path}, average importance: {avg_score:.2f}")