"""
Main compression engine for AutoLLMSE-DL skill.
Orchestrates backup, deduplication, importance scoring, and safe writing.
Compatible with Windows, Linux, and macOS.
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional
import platform

# Add scripts directory to path for imports
SCRIPTS_DIR = Path(__file__).parent
sys.path.append(str(SCRIPTS_DIR))

from backup_manager import BackupManager, create_backup_for_memory_files
from semantic_dedup import SemanticDeduplicator, deduplicate_memory_content
from importance_scoring import ImportanceScorer, score_memory_content


class MemoryCompressor:
    """Main orchestrator for memory file compression."""
    
    def __init__(self, workspace_dir: Path, config_path: Optional[Path] = None):
        self.workspace_dir = Path(workspace_dir)
        self.memory_dir = self.workspace_dir / "memory"
        self.hot_memory_dir = self.memory_dir / "hot"
        
        # Load configuration
        if config_path is None:
            config_path = self.workspace_dir / "skills" / "autollmse-dl" / "config" / "compression_rules.json"
        self.config = self._load_config(config_path)
        
        # Platform detection
        self.system = platform.system().lower()
        self.is_windows = self.system == "windows"
        
        # Initialize components
        self.backup_manager = BackupManager(self.workspace_dir)
        self.deduplicator = SemanticDeduplicator(self.workspace_dir)
        self.scorer = ImportanceScorer(self.workspace_dir)
    
    def _load_config(self, config_path: Path) -> dict:
        """Load compression configuration."""
        try:
            if config_path.exists():
                with open(config_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            else:
                return {}
        except Exception as e:
            print(f"Warning: Failed to load config {config_path}: {e}")
            return {}
    
    def _get_memory_files(self) -> List[Path]:
        """Get all memory files that need compression."""
        memory_files = []
        
        # Always include MEMORY.md
        memory_md = self.workspace_dir / "MEMORY.md"
        if memory_md.exists():
            memory_files.append(memory_md)
        
        # Include daily memory files
        if self.memory_dir.exists():
            for daily_file in self.memory_dir.glob("*.md"):
                if daily_file.name != "HOT_MEMORY.md" and daily_file.name != "unified_conversation_summary.md":
                    memory_files.append(daily_file)
        
        # Include hot memory files
        if self.hot_memory_dir.exists():
            hot_memory = self.hot_memory_dir / "HOT_MEMORY.md"
            if hot_memory.exists():
                memory_files.append(hot_memory)
        
        # Include unified summary
        unified_summary = self.memory_dir / "unified_conversation_summary.md"
        if unified_summary.exists():
            memory_files.append(unified_summary)
        
        return memory_files
    
    def _normalize_line_endings(self, content: str) -> str:
        """Normalize line endings to LF (Unix style)."""
        return content.replace('\r\n', '\n').replace('\r', '\n')
    
    def _get_encoding(self) -> str:
        """Get appropriate encoding for current platform."""
        return 'utf-8-sig' if self.is_windows else 'utf-8'
    
    def compress_files(self, file_paths: Optional[List[Path]] = None, 
                      preview_only: bool = False) -> Dict[str, dict]:
        """
        Compress specified memory files or all memory files if none specified.
        Returns dictionary with compression results.
        """
        if file_paths is None:
            file_paths = self._get_memory_files()
        
        if not file_paths:
            print("No memory files found to compress")
            return {}
        
        results = {}
        
        # Step 1: Create backups (unless preview mode)
        if not preview_only:
            print("Creating backups...")
            backup_results = create_backup_for_memory_files(file_paths, self.workspace_dir)
            results['backups'] = backup_results
        
        # Step 2: Load original content
        print("Loading original content...")
        original_content = {}
        for file_path in file_paths:
            if not file_path.exists():
                continue
            try:
                encoding = self._get_encoding()
                with open(file_path, 'r', encoding=encoding) as f:
                    original_content[str(file_path)] = f.read()
            except Exception as e:
                print(f"Warning: Failed to read {file_path}: {e}")
                original_content[str(file_path)] = ""
        
        # Step 3: Apply compression pipeline
        print("Applying semantic deduplication...")
        deduplicated_content = deduplicate_memory_content(file_paths, self.workspace_dir)
        
        print("Applying importance scoring...")
        scored_blocks = score_memory_content(file_paths, self.workspace_dir)
        
        # Step 4: Reconstruct compressed content
        print("Reconstructing compressed content...")
        compressed_content = {}
        
        for file_path_str, original in original_content.items():
            file_path = Path(file_path_str)
            filename = file_path.name
            
            # Get deduplicated content
            dedup_content = deduplicated_content.get(file_path_str, original)
            
            # Apply importance-based filtering if blocks are available
            if file_path_str in scored_blocks:
                blocks = scored_blocks[file_path_str]
                # Reconstruct from scored blocks (keep only high-importance ones)
                important_content = '\n\n'.join([
                    block['text'] for block in blocks 
                    if block.get('importance_score', 0) >= self.scorer.min_score_threshold
                ])
                if important_content.strip():
                    compressed_content[file_path_str] = important_content
                else:
                    compressed_content[file_path_str] = dedup_content
            else:
                compressed_content[file_path_str] = dedup_content
            
            # Normalize line endings
            compressed_content[file_path_str] = self._normalize_line_endings(
                compressed_content[file_path_str]
            )
        
        # Step 5: Calculate compression stats
        print("Calculating compression statistics...")
        for file_path_str in original_content:
            original_size = len(original_content[file_path_str])
            compressed_size = len(compressed_content[file_path_str])
            compression_ratio = (1 - compressed_size / original_size) * 100 if original_size > 0 else 0
            
            results[file_path_str] = {
                'original_size': original_size,
                'compressed_size': compressed_size,
                'compression_ratio': round(compression_ratio, 2),
                'preview_content': compressed_content[file_path_str][:500] + "..." if len(compressed_content[file_path_str]) > 500 else compressed_content[file_path_str]
            }
        
        # Step 6: Write compressed content (unless preview mode)
        if not preview_only:
            print("Writing compressed content...")
            self._write_compressed_content(compressed_content)
            results['status'] = 'completed'
        else:
            results['status'] = 'preview_only'
        
        return results
    
    def _write_compressed_content(self, compressed_content: Dict[str, str]):
        """Write compressed content to files with atomic operations."""
        encoding = self._get_encoding()
        
        for file_path_str, content in compressed_content.items():
            file_path = Path(file_path_str)
            
            # Create temporary file
            temp_path = file_path.with_suffix(file_path.suffix + '.tmp')
            
            try:
                # Write to temporary file
                with open(temp_path, 'w', encoding=encoding, newline='') as f:
                    f.write(content)
                
                # Atomic rename (works on all platforms)
                if file_path.exists():
                    file_path.unlink()
                temp_path.rename(file_path)
                
                # Preserve permissions on Unix-like systems
                if not self.is_windows:
                    original_stat = None
                    try:
                        original_stat = file_path.stat()
                    except FileNotFoundError:
                        pass
                    
                    if original_stat:
                        os.chmod(file_path, original_stat.st_mode)
                
            except Exception as e:
                print(f"Error writing compressed content to {file_path}: {e}")
                # Clean up temp file if it exists
                if temp_path.exists():
                    temp_path.unlink()
                raise
    
    def cleanup_old_backups(self, days_old: int = 30) -> int:
        """Clean up old backup files."""
        return self.backup_manager.cleanup_old_backups(days_old)


def main():
    """Main entry point for command line usage."""
    parser = argparse.ArgumentParser(description="AutoLLMSE-DL Memory Compressor")
    parser.add_argument('--all', action='store_true', help='Compress all memory files')
    parser.add_argument('--file', type=str, help='Compress specific file')
    parser.add_argument('--preview', action='store_true', help='Preview compression without writing')
    parser.add_argument('--auto', action='store_true', help='Run in automatic mode (for heartbeat)')
    parser.add_argument('--workspace', type=str, help='Workspace directory path')
    parser.add_argument('--platform', type=str, choices=['windows', 'linux', 'darwin', 'unix'], 
                       help='Override platform detection')
    
    args = parser.parse_args()
    
    # Determine workspace directory
    if args.workspace:
        workspace_dir = Path(args.workspace)
    else:
        workspace_dir = Path.home() / ".openclaw" / "workspace"
    
    if not workspace_dir.exists():
        print(f"Error: Workspace directory not found: {workspace_dir}")
        sys.exit(1)
    
    # Override platform if specified
    if args.platform:
        original_system = platform.system().lower()
        platform.system = lambda: args.platform.capitalize()
    
    try:
        compressor = MemoryCompressor(workspace_dir)
        
        if args.file:
            file_paths = [Path(args.file)]
        elif args.all or args.auto:
            file_paths = None  # Use all memory files
        else:
            print("Error: Specify --all, --file, or --auto")
            sys.exit(1)
        
        results = compressor.compress_files(file_paths, preview_only=args.preview)
        
        # Print results
        print("\n" + "="*60)
        print("COMPRESSION RESULTS")
        print("="*60)
        
        if results.get('status') == 'preview_only':
            print("PREVIEW MODE - No files were modified")
        elif results.get('status') == 'completed':
            print("COMPRESSION COMPLETED - Files have been updated")
        
        for file_path, stats in results.items():
            if file_path in ['backups', 'status']:
                continue
            print(f"\n{file_path}:")
            print(f"  Original size: {stats['original_size']} bytes")
            print(f"  Compressed size: {stats['compressed_size']} bytes")
            print(f"  Compression ratio: {stats['compression_ratio']:.2f}%")
            if args.preview:
                print(f"  Preview: {stats['preview_content']}")
        
        # Cleanup old backups in auto mode
        if args.auto:
            deleted_count = compressor.cleanup_old_backups(days_old=7)
            if deleted_count > 0:
                print(f"\nCleaned up {deleted_count} old backup files")
        
        print("\n" + "="*60)
        
    except Exception as e:
        print(f"Error during compression: {e}")
        sys.exit(1)
    finally:
        # Restore original platform detection if overridden
        if args.platform:
            platform.system = lambda: original_system.capitalize()


if __name__ == "__main__":
    main()