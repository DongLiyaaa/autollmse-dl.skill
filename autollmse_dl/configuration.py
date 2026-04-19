"""Helpers for loading compression configuration."""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Optional

WORKSPACE_CONFIG_RELATIVE_PATH = (
    Path("skills") / "autollmse-dl" / "config" / "compression_rules.json"
)


def load_config(workspace_dir: Optional[Path] = None, config_path: Optional[Path] = None) -> dict:
    """Load compression configuration from an explicit path, workspace override, or package defaults."""
    candidates = []

    if config_path is not None:
        candidates.append(Path(config_path))

    if workspace_dir is not None:
        candidates.append(Path(workspace_dir) / WORKSPACE_CONFIG_RELATIVE_PATH)

    for candidate in candidates:
        if candidate.exists():
            with candidate.open("r", encoding="utf-8") as handle:
                return json.load(handle)

    packaged_config = resources.files("autollmse_dl").joinpath("config/compression_rules.json")
    return json.loads(packaged_config.read_text(encoding="utf-8"))
