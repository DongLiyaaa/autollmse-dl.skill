"""
Cross-platform tests for AutoLLMSE-DL skill.
"""

import unittest
import tempfile
import os
import sys
from pathlib import Path
import platform

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from backup_manager import BackupManager
from semantic_dedup import SemanticDeduplicator
from importance_scoring import ImportanceScorer
from compressor import MemoryCompressor


class TestCrossPlatform(unittest.TestCase):
    """Test cross-platform compatibility."""
    
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.workspace_dir = self.temp_dir / "workspace"
        self.workspace_dir.mkdir()
        
        # Create memory directory structure
        (self.workspace_dir / "memory").mkdir()
        (self.workspace_dir / "memory" / "hot").mkdir()
        
        # Create test files
        self.memory_md = self.workspace_dir / "MEMORY.md"
        self.daily_memory = self.workspace_dir / "memory" / "2026-04-20.md"
        self.hot_memory = self.workspace_dir / "memory" / "hot" / "HOT_MEMORY.md"
        
        with open(self.memory_md, 'w', encoding='utf-8') as f:
            f.write("# MEMORY.md\n\nCore identity and important configurations.\n")
        
        with open(self.daily_memory, 'w', encoding='utf-8') as f:
            f.write("## Daily Memory\n\nEvents from 2026-04-20.\n")
        
        with open(self.hot_memory, 'w', encoding='utf-8') as f:
            f.write("# HOT_MEMORY.md\n\nCurrent active session data.\n")
    
    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir)
    
    def test_backup_manager(self):
        """Test backup manager works across platforms."""
        backup_manager = BackupManager(self.workspace_dir)
        backup_path = backup_manager.create_backup(self.memory_md)
        
        self.assertIsNotNone(backup_path)
        self.assertTrue(backup_path.exists())
        self.assertEqual(backup_path.suffix, '.bak')
    
    def test_compressor_initialization(self):
        """Test compressor initializes correctly on all platforms."""
        compressor = MemoryCompressor(self.workspace_dir)
        
        # Should detect correct platform
        system = platform.system().lower()
        if system == 'windows':
            self.assertTrue(compressor.is_windows)
        else:
            self.assertFalse(compressor.is_windows)
    
    def test_file_detection(self):
        """Test memory file detection works correctly."""
        compressor = MemoryCompressor(self.workspace_dir)
        memory_files = compressor._get_memory_files()
        
        expected_files = {str(self.memory_md), str(self.daily_memory), str(self.hot_memory)}
        actual_files = {str(f) for f in memory_files}
        
        self.assertEqual(expected_files, actual_files)
    
    def test_line_ending_normalization(self):
        """Test line ending normalization works correctly."""
        compressor = MemoryCompressor(self.workspace_dir)
        
        # Test Windows line endings
        windows_content = "line1\r\nline2\r\nline3"
        normalized = compressor._normalize_line_endings(windows_content)
        self.assertEqual(normalized, "line1\nline2\nline3")
        
        # Test old Mac line endings  
        mac_content = "line1\rline2\rline3"
        normalized = compressor._normalize_line_endings(mac_content)
        self.assertEqual(normalized, "line1\nline2\nline3")
        
        # Test Unix line endings (should remain unchanged)
        unix_content = "line1\nline2\nline3"
        normalized = compressor._normalize_line_endings(unix_content)
        self.assertEqual(normalized, unix_content)


if __name__ == "__main__":
    unittest.main()
