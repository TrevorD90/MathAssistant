"""Dev command: `python -m mathassistant`.

Builds the frontend if it is missing or older than its sources (dev only),
then starts the local server and opens the browser.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys

from .config import load_config
from .log_redact import setup_logging
from .paths import is_frozen, repo_root, web_dist_dir


def _web_is_stale() -> bool:
    dist_index = web_dist_dir() / "index.html"
    if not dist_index.exists():
        return True
    built = dist_index.stat().st_mtime
    web = repo_root() / "web"
    sources = [*(web / "src").rglob("*"), web / "index.html", web / "package.json", web / "vite.config.ts"]
    return any(p.is_file() and p.stat().st_mtime > built for p in sources)


def _build_web() -> None:
    npm = shutil.which("npm")
    if npm is None:
        sys.exit("npm not found. Install Node.js 20+, then run: cd web && npm install && npm run build")
    web = repo_root() / "web"
    if not (web / "node_modules").exists():
        print("Installing frontend dependencies (first run)...")
        subprocess.run([npm, "install"], cwd=web, check=True)
    print("Building frontend...")
    subprocess.run([npm, "run", "build"], cwd=web, check=True)


def main() -> None:
    # Windowed (no-console) builds have no stdout/stderr; give libraries a sink.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")  # noqa: SIM115 - process lifetime
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")  # noqa: SIM115
    config = load_config()
    setup_logging()
    if "--self-test" in sys.argv:
        from .server import self_test

        sys.exit(self_test())
    if not is_frozen() and "--no-build" not in sys.argv and _web_is_stale():
        _build_web()
    from .server import run

    run(config)


if __name__ == "__main__":
    main()
