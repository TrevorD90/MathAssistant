"""Process configuration (dev flags). Non-secret user settings live in SQLite.

`.env` is read only in development (never when bundled), and only the names in
`.env.example` are used. The dev key is honoured only when DEV_MODE=true.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from .paths import is_frozen, repo_root


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "on")


def load_dotenv_if_dev() -> None:
    if is_frozen():
        return
    env_file = repo_root() / ".env"
    if env_file.exists():
        from dotenv import load_dotenv  # BSD-3; dev only

        load_dotenv(env_file, override=False)


@dataclass(frozen=True)
class Config:
    dev_mode: bool
    fixed_port: int | None
    open_browser: bool


def load_config() -> Config:
    load_dotenv_if_dev()
    port = os.environ.get("MATHASSISTANT_PORT", "").strip()
    return Config(
        dev_mode=_truthy(os.environ.get("DEV_MODE")) and not is_frozen(),
        fixed_port=int(port) if port.isdigit() else None,
        open_browser=not _truthy(os.environ.get("MATHASSISTANT_NO_BROWSER")),
    )


def dev_api_key() -> str | None:
    """The dev key from .env, honoured only when DEV_MODE=true (never in bundled builds)."""
    if is_frozen() or not _truthy(os.environ.get("DEV_MODE")):
        return None
    key = os.environ.get("ANTHROPIC_DEV_API_KEY", "").strip()
    return key or None
