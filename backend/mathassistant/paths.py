"""File locations for dev and PyInstaller-bundled modes.

* Bundled resources (the built web app) come from `sys._MEIPASS` when frozen,
  or the repo checkout in development.
* User data (SQLite, logs) always lives under `platformdirs`, never next to the
  executable, so it survives app updates (spec §10, §12.4).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from platformdirs import user_data_dir, user_log_dir

# Internal app ID. NEVER change: keyring service name and data folder derive from it.
APP_ID = "mathassistant"
APP_NAME = "MathAssistant"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False)) and hasattr(sys, "_MEIPASS")


def repo_root() -> Path:
    """Repository root in development (backend/mathassistant/paths.py -> repo)."""
    return Path(__file__).resolve().parents[2]


def web_dist_dir() -> Path:
    if is_frozen():
        return Path(sys._MEIPASS) / "web_dist"  # type: ignore[attr-defined]
    return repo_root() / "web" / "dist"


def data_dir() -> Path:
    # MATHASSISTANT_DATA_DIR lets tests use a temp folder.
    override = os.environ.get("MATHASSISTANT_DATA_DIR")
    path = Path(override) if override else Path(user_data_dir(APP_ID, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def log_dir() -> Path:
    override = os.environ.get("MATHASSISTANT_DATA_DIR")
    path = Path(override) / "logs" if override else Path(user_log_dir(APP_ID, appauthor=False))
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path() -> Path:
    return data_dir() / "mathassistant.sqlite3"
