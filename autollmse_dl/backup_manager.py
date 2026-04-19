"""Cross-platform backup utilities."""

from __future__ import annotations

import os
import shutil
import time
from pathlib import Path
from typing import Optional


class BackupManager:
    """Manage rotating backups for memory files."""

    def __init__(self, workspace_dir: Path, max_versions: int = 3):
        self.workspace_dir = Path(workspace_dir)
        self.max_versions = max_versions
        self.memory_dir = self.workspace_dir / "memory"
        self.hot_memory_dir = self.memory_dir / "hot"

    def create_backup(self, file_path: Path) -> Optional[Path]:
        """Create or rotate a backup for ``file_path``."""
        file_path = Path(file_path)
        if not file_path.exists():
            return None

        primary_backup = file_path.with_suffix(file_path.suffix + ".bak")

        try:
            if primary_backup.exists():
                timestamp = time.strftime("%Y%m%d%H%M%S", time.localtime(primary_backup.stat().st_mtime))
                rotated_backup = file_path.with_name(f"{file_path.name}_{timestamp}.bak")
                primary_backup.replace(rotated_backup)

            shutil.copy2(file_path, primary_backup)

            if os.name != "nt":
                os.chmod(primary_backup, file_path.stat().st_mode)

            self._prune_backups(file_path)
            return primary_backup
        except Exception as exc:
            print(f"Warning: Failed to create backup for {file_path}: {exc}")
            return None

    def _get_backup_files(self, original_file: Path) -> list[Path]:
        pattern = f"{original_file.name}*.bak"
        return sorted(
            (path for path in original_file.parent.glob(pattern) if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def _prune_backups(self, original_file: Path) -> None:
        for obsolete_backup in self._get_backup_files(original_file)[self.max_versions :]:
            try:
                obsolete_backup.unlink()
            except Exception as exc:
                print(f"Warning: Failed to remove old backup {obsolete_backup}: {exc}")

    def restore_backup(self, original_file: Path, version: int = 0) -> bool:
        """Restore the requested backup version for ``original_file``."""
        backups = self._get_backup_files(Path(original_file))
        if version < 0 or version >= len(backups):
            return False

        try:
            shutil.copy2(backups[version], original_file)
            return True
        except Exception as exc:
            print(f"Error restoring backup for {original_file}: {exc}")
            return False

    def get_backup_info(self, original_file: Path) -> dict:
        """Return metadata for backups of ``original_file``."""
        backups = self._get_backup_files(Path(original_file))
        return {
            "original_file": str(original_file),
            "backup_count": len(backups),
            "backups": [
                {
                    "version": index,
                    "path": str(backup),
                    "size": backup.stat().st_size,
                    "modified": backup.stat().st_mtime,
                    "human_time": time.ctime(backup.stat().st_mtime),
                }
                for index, backup in enumerate(backups)
            ],
        }

    def cleanup_old_backups(self, days_old: int = 30) -> int:
        """Delete backups older than ``days_old`` days."""
        cutoff_time = time.time() - (days_old * 24 * 3600)
        deleted_count = 0

        directories = [self.workspace_dir, self.memory_dir, self.hot_memory_dir]
        if self.memory_dir.exists():
            directories.extend(path for path in self.memory_dir.iterdir() if path.is_dir())

        seen = set()
        for directory in directories:
            directory = Path(directory)
            if not directory.exists() or directory in seen:
                continue
            seen.add(directory)

            for backup_file in directory.glob("*.bak*"):
                if backup_file.is_file() and backup_file.stat().st_mtime < cutoff_time:
                    try:
                        backup_file.unlink()
                        deleted_count += 1
                    except Exception as exc:
                        print(f"Warning: Failed to delete old backup {backup_file}: {exc}")

        return deleted_count


def create_backup_for_memory_files(memory_files: list[Path], workspace_dir: Path) -> dict:
    """Create backups for all specified memory files."""
    manager = BackupManager(workspace_dir)
    results = {}

    for file_path in memory_files:
        backup_path = manager.create_backup(file_path)
        results[str(file_path)] = {
            "success": backup_path is not None,
            "backup_path": str(backup_path) if backup_path else None,
        }

    return results
