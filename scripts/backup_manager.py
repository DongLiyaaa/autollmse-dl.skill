"""
Cross-platform backup manager for AutoLLMSE-DL skill.
Handles automatic backup creation, version retention, and rollback operations.
Compatible with Windows, Linux, and macOS.
"""

import os
import shutil
import time
from pathlib import Path
from typing import List, Optional
import platform


class BackupManager:
    """Manages backups of memory files across platforms."""
    
    def __init__(self, workspace_dir: Path, max_versions: int = 3):
        self.workspace_dir = Path(workspace_dir)
        self.max_versions = max_versions
        self.memory_dir = self.workspace_dir / "memory"
        self.hot_memory_dir = self.memory_dir / "hot"
        
        # Platform-specific settings
        self.system = platform.system().lower()
        if self.system == "windows":
            self.backup_ext = ".bak"
            self.version_sep = "_"
        else:
            self.backup_ext = ".bak"
            self.version_sep = "_"
    
    def create_backup(self, file_path: Path) -> Optional[Path]:
        """
        Create a backup of the specified file.
        Returns the backup file path or None if backup failed.
        """
        if not file_path.exists():
            return None
            
        try:
            # Create backup filename
            backup_path = file_path.with_suffix(file_path.suffix + self.backup_ext)
            
            # If backup already exists, rotate versions
            if backup_path.exists():
                self._rotate_backups(file_path)
            
            # Create new backup
            shutil.copy2(file_path, backup_path)
            
            # Ensure proper permissions (Unix-like systems)
            if self.system != "windows":
                backup_stat = file_path.stat()
                os.chmod(backup_path, backup_stat.st_mode)
            
            return backup_path
            
        except Exception as e:
            print(f"Warning: Failed to create backup for {file_path}: {e}")
            return None
    
    def _rotate_backups(self, original_file: Path):
        """Rotate backup versions, keeping only max_versions."""
        backup_files = self._get_backup_files(original_file)
        
        # Sort by modification time (newest first)
        backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Remove excess backups
        for old_backup in backup_files[self.max_versions - 1:]:
            try:
                old_backup.unlink()
            except Exception as e:
                print(f"Warning: Failed to remove old backup {old_backup}: {e}")
    
    def _get_backup_files(self, original_file: Path) -> List[Path]:
        """Get all backup files for the original file."""
        backup_files = []
        base_name = original_file.name
        
        # Look for .bak files
        for file_path in original_file.parent.glob(f"{base_name}*.bak*"):
            if file_path.is_file():
                backup_files.append(file_path)
        
        return backup_files
    
    def restore_backup(self, original_file: Path, version: int = 0) -> bool:
        """
        Restore a specific backup version.
        version=0 means most recent backup.
        Returns True if successful, False otherwise.
        """
        backup_files = self._get_backup_files(original_file)
        if not backup_files:
            return False
            
        backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        if version >= len(backup_files):
            return False
            
        try:
            backup_to_restore = backup_files[version]
            shutil.copy2(backup_to_restore, original_file)
            return True
        except Exception as e:
            print(f"Error restoring backup: {e}")
            return False
    
    def get_backup_info(self, original_file: Path) -> dict:
        """Get information about available backups."""
        backup_files = self._get_backup_files(original_file)
        backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        info = {
            "original_file": str(original_file),
            "backup_count": len(backup_files),
            "backups": []
        }
        
        for i, backup_file in enumerate(backup_files):
            info["backups"].append({
                "version": i,
                "path": str(backup_file),
                "size": backup_file.stat().st_size,
                "modified": backup_file.stat().st_mtime,
                "human_time": time.ctime(backup_file.stat().st_mtime)
            })
        
        return info
    
    def cleanup_old_backups(self, days_old: int = 30) -> int:
        """
        Clean up backups older than specified days.
        Returns number of files deleted.
        """
        cutoff_time = time.time() - (days_old * 24 * 3600)
        deleted_count = 0
        
        # Check all memory directories
        dirs_to_check = [self.memory_dir, self.hot_memory_dir]
        if self.memory_dir.exists():
            dirs_to_check.extend([d for d in self.memory_dir.iterdir() if d.is_dir()])
        
        for check_dir in dirs_to_check:
            if not check_dir.exists():
                continue
                
            for backup_file in check_dir.glob("*.bak*"):
                if backup_file.is_file() and backup_file.stat().st_mtime < cutoff_time:
                    try:
                        backup_file.unlink()
                        deleted_count += 1
                    except Exception as e:
                        print(f"Warning: Failed to delete old backup {backup_file}: {e}")
        
        return deleted_count


def create_backup_for_memory_files(memory_files: List[Path], workspace_dir: Path) -> dict:
    """
    Create backups for all specified memory files.
    Returns dictionary with backup results.
    """
    backup_manager = BackupManager(workspace_dir)
    results = {}
    
    for file_path in memory_files:
        backup_path = backup_manager.create_backup(file_path)
        results[str(file_path)] = {
            "success": backup_path is not None,
            "backup_path": str(backup_path) if backup_path else None
        }
    
    return results


if __name__ == "__main__":
    # Example usage
    workspace = Path.home() / ".openclaw" / "workspace"
    memory_files = [
        workspace / "MEMORY.md",
        workspace / "memory" / "2026-04-20.md"
    ]
    
    results = create_backup_for_memory_files(memory_files, workspace)
    print("Backup results:", results)