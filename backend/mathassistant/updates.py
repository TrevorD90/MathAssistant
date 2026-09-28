"""Optional update check (spec §12.4).

On launch (if enabled in Settings; on by default) ask the GitHub Releases API
for the latest release and compare its tag with our version. This request
sends nothing about the user: a plain GET for a public URL. It runs in a
background thread and never blocks or breaks the app; failures are ignored.
"""

from __future__ import annotations

import json
import logging
import re
import threading
import urllib.request
from dataclasses import dataclass

from . import __version__

log = logging.getLogger(__name__)

REPO = "TrevorD90/MathAssistant"
LATEST_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPO}/releases/latest"
TIMEOUT_S = 6


def parse_version(v: str) -> tuple[int, ...] | None:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (v or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    return bool(a and b and a > b)


@dataclass
class UpdateInfo:
    checked: bool = False
    available: bool = False
    latest: str = ""
    url: str = RELEASES_PAGE

    def to_dict(self) -> dict:
        return {"checked": self.checked, "available": self.available, "latest": self.latest, "url": self.url}


def fetch_latest(opener=urllib.request.urlopen) -> str | None:
    """Tag name of the latest release, or None (network error, no releases...)."""
    req = urllib.request.Request(LATEST_URL, headers={
        "Accept": "application/vnd.github+json",
        "User-Agent": f"MathAssistant/{__version__}",
    })
    try:
        with opener(req, timeout=TIMEOUT_S) as resp:
            data = json.loads(resp.read(200_000).decode("utf-8"))
    except Exception as exc:  # offline, rate-limited, no releases yet (404)...
        log.info("update check skipped: %s", type(exc).__name__)
        return None
    tag = data.get("tag_name") if isinstance(data, dict) else None
    return tag if isinstance(tag, str) else None


class UpdateChecker:
    def __init__(self, opener=urllib.request.urlopen):
        self.info = UpdateInfo()
        self._opener = opener
        self._lock = threading.Lock()

    def run_once(self) -> UpdateInfo:
        tag = fetch_latest(self._opener)
        with self._lock:
            self.info = UpdateInfo(checked=tag is not None, available=bool(tag and is_newer(tag)),
                                   latest=(tag or "").lstrip("v"))
        if self.info.available:
            log.info("update available: %s", self.info.latest)
        return self.info

    def start_background(self) -> None:
        threading.Thread(target=self.run_once, name="update-check", daemon=True).start()
