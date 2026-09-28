"""Logging with secret redaction (spec §11.1, N9).

* Every handler gets `RedactFilter`, which replaces any registered secret and
  anything shaped like an API key with `[REDACTED]`.
* `scrub()` is applied to any provider-derived string before logging/display.
* Logs go to the platformdirs log folder (rotating) and stderr.
"""

from __future__ import annotations

import logging
import re
import threading
from logging.handlers import RotatingFileHandler

from .paths import log_dir

# Shapes of common provider keys (Anthropic, OpenAI, Google, OpenRouter).
_KEY_PATTERNS = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"sk-(?:proj-|or-)?[A-Za-z0-9_\-]{16,}"),
    re.compile(r"AIza[0-9A-Za-z_\-]{20,}"),
]

_secrets: set[str] = set()
_lock = threading.Lock()


def register_secret(value: str | None) -> None:
    """Remember a secret so it is redacted anywhere it appears."""
    if value and len(value) >= 8:
        with _lock:
            _secrets.add(value)


def forget_secret(value: str | None) -> None:
    with _lock:
        _secrets.discard(value or "")


def scrub(text: str) -> str:
    if not text:
        return text
    with _lock:
        secrets = list(_secrets)
    for s in secrets:
        text = text.replace(s, "[REDACTED]")
    for pat in _KEY_PATTERNS:
        text = pat.sub("[REDACTED]", text)
    return text


class RedactFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = scrub(msg)
        record.args = None
        if record.exc_info and record.exc_info[1] is not None:
            # Render the traceback now, scrubbed, and drop the raw exception.
            formatted = logging.Formatter().formatException(record.exc_info)
            record.msg = f"{record.msg}\n{scrub(formatted)}"
            record.exc_info = None
            record.exc_text = None
        return True


_configured = False
_factory_installed = False


def install_record_factory() -> None:
    """Scrub every LogRecord at creation, so *any* handler (ours or a library's)
    only ever sees redacted text. Handler filters alone miss foreign handlers."""
    global _factory_installed
    if _factory_installed:
        return
    base_factory = logging.getLogRecordFactory()

    def factory(*args, **kwargs):
        record = base_factory(*args, **kwargs)
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(record.msg)
        record.msg = scrub(msg)
        record.args = None
        return record

    logging.setLogRecordFactory(factory)
    _factory_installed = True


# Installed on import: nothing should log before this module is loaded.
install_record_factory()


def setup_logging(level: int = logging.INFO) -> None:
    global _configured
    if _configured:
        return
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    file_handler = RotatingFileHandler(log_dir() / "mathassistant.log", maxBytes=1_000_000,
                                       backupCount=3, encoding="utf-8")
    stream_handler = logging.StreamHandler()
    for h in (file_handler, stream_handler):
        h.setFormatter(fmt)
        h.addFilter(RedactFilter())
        root.addHandler(h)
    # SDK/HTTP libraries can log request details at DEBUG; keep them quiet.
    for noisy in ("anthropic", "httpx", "httpx2", "httpcore", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    _configured = True
