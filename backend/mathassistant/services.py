"""Shared app services: storage, settings, provider construction, engine."""

from __future__ import annotations

import json
import logging
import os
import secrets
import threading
import time
from typing import Callable

from . import __version__, key_store
from .updates import UpdateChecker
from .engine import extract as extract_mod
from .engine.turn_loop import TutorEngine, TutorError
from .providers import registry
from .providers.base import Capabilities, LLMProvider, ProviderError, Usage
from .storage import Storage

log = logging.getLogger(__name__)

# settings table keys (non-secret)
S_PROVIDER = "provider"
S_MODEL = "model"
S_KEY_OK = "key_verified"          # "1" after a successful Test key for provider+model
S_CAPS = "capabilities_json"
S_UPDATE_CHECK = "update_check"    # "1" (default) or "0" (§12.4)


class Services:
    def __init__(self, storage: Storage,
                 provider_factory: Callable[[], LLMProvider] | None = None,
                 dev_mode: bool = False):
        self.storage = storage
        self.dev_mode = dev_mode
        # Tests inject a FakeProvider factory; production builds from settings + keyring.
        if provider_factory is None and dev_mode and os.environ.get("MATHASSISTANT_DEMO") == "1":
            # Dev-only offline demo (never in bundled builds: dev_mode is False when frozen).
            from .providers.demo_provider import DemoProvider

            demo = DemoProvider()
            provider_factory = lambda: demo  # noqa: E731
            log.warning("DEMO provider active: canned responses, no AI")
        self._provider_factory_override = provider_factory
        self.engine = TutorEngine(storage, self.make_provider)
        self.shutdown: Callable[[], None] = lambda: None
        # Vision-call usage waiting to be added to the problem it becomes
        # (extraction_id -> (Usage, created_at)). In memory only; no image data.
        self._pending_usage: dict[str, tuple[Usage, float]] = {}
        self.updates = UpdateChecker()
        self._pending_lock = threading.Lock()

    # ------------------------------------------------------------ settings

    def provider_id(self) -> str:
        return self.storage.get_setting(S_PROVIDER, registry.DEFAULT_PROVIDER) or registry.DEFAULT_PROVIDER

    def model_id(self) -> str:
        return self.storage.get_setting(S_MODEL, registry.DEFAULT_MODEL) or registry.DEFAULT_MODEL

    def capabilities(self) -> Capabilities:
        raw = self.storage.get_setting(S_CAPS)
        if not raw:
            return Capabilities(vision=True, structured_output=True, streaming=True)
        try:
            d = json.loads(raw)
            return Capabilities(**{k: bool(d.get(k)) for k in ("vision", "structured_output", "streaming")})
        except (ValueError, TypeError):
            return Capabilities()

    def set_model(self, provider: str, model: str) -> None:
        if provider not in registry.PROVIDERS:
            raise TutorError("Unknown provider.", "bad_request")
        model = model.strip()
        if not model or len(model) > 100 or not all(c.isalnum() or c in "-._:/" for c in model):
            raise TutorError("Enter a valid model name.", "bad_request")
        changed = (provider != self.provider_id()) or (model != self.model_id())
        self.storage.set_setting(S_PROVIDER, provider)
        self.storage.set_setting(S_MODEL, model)
        if changed:
            # A different model must pass Test key again (capability probe).
            self.storage.set_setting(S_KEY_OK, "0")

    def update_check_enabled(self) -> bool:
        return self.storage.get_setting(S_UPDATE_CHECK, "1") == "1"

    def set_update_check(self, enabled: bool) -> None:
        self.storage.set_setting(S_UPDATE_CHECK, "1" if enabled else "0")

    def key_verified(self) -> bool:
        return self.storage.get_setting(S_KEY_OK) == "1"

    # ------------------------------------------------------------ provider

    def make_provider(self) -> LLMProvider:
        if self._provider_factory_override is not None:
            return self._provider_factory_override()
        provider = self.provider_id()
        try:
            key = key_store.get_key(provider)
        except key_store.KeyStoreUnavailable:
            raise TutorError(ProviderError("keystore_unavailable").user_message, "keystore_unavailable") from None
        if not key:
            raise TutorError(ProviderError("no_key").user_message, "no_key")
        if not self.key_verified():
            raise TutorError("Test your API key in Settings before starting.", "key_not_verified")
        return registry.create_provider(provider, self.model_id(), key, self.capabilities())

    def test_key(self, provider: str, model: str, new_key: str | None) -> dict:
        """Test a new key (then store it) or the stored key. Runs the capability probe."""
        self.set_model(provider, model)
        if self._provider_factory_override is not None:
            p = self._provider_factory_override()
        else:
            try:
                key = new_key.strip() if new_key else key_store.get_key(provider)
            except key_store.KeyStoreUnavailable:
                raise TutorError(ProviderError("keystore_unavailable").user_message, "keystore_unavailable") from None
            if not key:
                raise TutorError(ProviderError("no_key").user_message, "no_key")
            from . import log_redact
            log_redact.register_secret(key)
            p = registry.create_provider(provider, model, key)
        try:
            caps = p.probe()
        except ProviderError as err:
            self.storage.set_setting(S_KEY_OK, "0")
            raise TutorError(err.user_message, err.kind) from None
        if new_key and self._provider_factory_override is None:
            try:
                key_store.set_key(provider, new_key)
            except key_store.KeyStoreUnavailable:
                raise TutorError(ProviderError("keystore_unavailable").user_message, "keystore_unavailable") from None
        self.storage.set_setting(S_CAPS, json.dumps(caps.__dict__, sort_keys=True))
        self.storage.set_setting(S_KEY_OK, "1")
        log.info("key test passed: provider=%s model=%s structured=%s", provider, model, caps.structured_output)
        return {"ok": True, "capabilities": caps.__dict__}

    # ------------------------------------------------------------ images (Phase 2)

    def extract_image(self, image_base64: str, media_type: str) -> dict:
        """One vision call: image -> problem text for the learner to confirm."""
        if not self.capabilities().vision:
            raise TutorError("The selected model can't read images. Type the problem instead, "
                             "or pick a model that supports images in Settings.", "missing_capability")
        try:
            image = extract_mod.decode_image(image_base64, media_type)
        except extract_mod.ImageError as exc:
            raise TutorError(str(exc), "bad_image") from None
        provider = self.make_provider()
        try:
            ex = extract_mod.extract_problems(provider, image, media_type)
        except ProviderError as err:
            raise TutorError(err.user_message, err.kind) from None
        finally:
            del image  # never kept
        extraction_id = secrets.token_urlsafe(12)
        with self._pending_lock:
            now = time.monotonic()
            # Drop stale entries (abandoned confirmations) after an hour.
            self._pending_usage = {k: v for k, v in self._pending_usage.items() if now - v[1] < 3600}
            self._pending_usage[extraction_id] = (ex.usage, now)
        return {
            "extraction_id": extraction_id,
            "readable": ex.readable,
            "note": ex.note,
            "problems": [p.to_dict() for p in ex.problems],
        }

    def take_extraction_usage(self, extraction_ids: list[str]) -> list[Usage]:
        """Usage of the vision call(s) that produced this problem (each counted once)."""
        out: list[Usage] = []
        with self._pending_lock:
            for eid in extraction_ids:
                item = self._pending_usage.pop(eid, None)
                if item:
                    out.append(item[0])
        return out

    def remove_key(self, provider: str) -> None:
        if self._provider_factory_override is None:
            try:
                key_store.delete_key(provider)
            except key_store.KeyStoreUnavailable:
                raise TutorError(ProviderError("keystore_unavailable").user_message, "keystore_unavailable") from None
        self.storage.set_setting(S_KEY_OK, "0")

    def status(self) -> dict:
        provider, model = self.provider_id(), self.model_id()
        keystore_ok = True
        if self._provider_factory_override is not None:
            has_key = True
        else:
            try:
                has_key = bool(key_store.get_key(provider))
            except key_store.KeyStoreUnavailable:
                has_key, keystore_ok = False, False
        tested = registry.is_tested(provider, model)
        return {
            "provider": provider,
            "model": model,
            "has_key": has_key,
            "key_verified": has_key and self.key_verified(),
            "keystore_available": keystore_ok,
            "tutoring_enabled": has_key and self.key_verified(),
            "tested": tested,
            "untested_warning": None if tested else registry.UNTESTED_WARNING,
            "known_model": registry.model_info(provider, model) is not None,
            "capabilities": self.capabilities().__dict__,
            "dev_mode": self.dev_mode,
            "version": __version__,
            "update_check": self.update_check_enabled(),
            "update": self.updates.info.to_dict(),
        }
