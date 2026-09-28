"""API key storage in the OS credential store (spec §11.1, N9).

Windows Credential Manager / macOS Keychain via `keyring` (MIT). If no secure
backend is available we raise — never fall back to a plain-text file.

The key never touches SQLite, config files, or logs. In development only,
`DEV_MODE=true` + `ANTHROPIC_DEV_API_KEY` in `.env` is used when the OS store
has no key.
"""

from __future__ import annotations

import os

import keyring
import keyring.errors

from . import log_redact
from .config import dev_api_key
from .paths import APP_ID


class KeyStoreUnavailable(RuntimeError):
    pass


def _service() -> str:
    # Tests set MATHASSISTANT_KEYRING_SERVICE so they never touch the real entry.
    return os.environ.get("MATHASSISTANT_KEYRING_SERVICE", APP_ID)


def _username(provider: str) -> str:
    return f"{provider}-api-key"


def _check_backend() -> None:
    kr = keyring.get_keyring()
    mod = type(kr).__module__
    name = type(kr).__name__
    # fail.Keyring = no backend; keyrings.alt plaintext/encrypted-file backends are not acceptable.
    if mod.startswith("keyring.backends.fail") or mod.startswith("keyrings.alt") or "Plaintext" in name:
        raise KeyStoreUnavailable(f"no secure credential store ({name})")


def get_key(provider: str) -> str | None:
    """Stored key for `provider`, or the dev key (DEV_MODE only). Registers it for redaction."""
    key: str | None = None
    try:
        _check_backend()
        key = keyring.get_password(_service(), _username(provider))
    except KeyStoreUnavailable:
        key = None
        if not dev_api_key():
            raise
    except keyring.errors.KeyringError as exc:
        raise KeyStoreUnavailable(type(exc).__name__) from None
    if not key and provider == "anthropic":
        key = dev_api_key()
    log_redact.register_secret(key)
    return key


def has_key(provider: str) -> bool:
    try:
        return bool(get_key(provider))
    except KeyStoreUnavailable:
        return False


def set_key(provider: str, key: str) -> None:
    key = key.strip()
    if not key:
        raise ValueError("empty key")
    log_redact.register_secret(key)
    _check_backend()
    try:
        keyring.set_password(_service(), _username(provider), key)
    except keyring.errors.KeyringError as exc:
        raise KeyStoreUnavailable(type(exc).__name__) from None


def delete_key(provider: str) -> None:
    _check_backend()
    try:
        # The removed key stays registered for redaction for the rest of the session.
        keyring.delete_password(_service(), _username(provider))
    except keyring.errors.PasswordDeleteError:
        pass  # nothing stored
    except keyring.errors.KeyringError as exc:
        raise KeyStoreUnavailable(type(exc).__name__) from None
