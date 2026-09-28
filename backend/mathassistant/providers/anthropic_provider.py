"""Anthropic (Claude) adapter (spec §11.2, Phase 1 provider).

* Structured output via `output_config.format` (JSON schema). If a model
  rejects it, the adapter falls back to prompt-only JSON for that model
  (capability `structured_output=False`, detected by `probe()`).
* Prompt caching: every system block except the last carries
  `cache_control` so the stable prefix (system prompt, then per-problem
  context) is cached where the model's minimum prefix length allows.
  Note: Haiku 4.5's minimum cacheable prefix is 4096 tokens, so caching is a
  no-op there with our short prompts; it applies on Sonnet 5 (>=1024).
* Vision: image content blocks pass straight through `messages` (see
  engine/extract.py); `probe()` detects whether the model accepts images.
* Errors are mapped to fixed `ProviderError` kinds. Provider error text is
  never surfaced or logged verbatim (it can echo request details).
"""

from __future__ import annotations

import base64
import json
import logging

import anthropic

from .base import (
    Capabilities,
    LLMProvider,
    ProviderError,
    StructuredRequest,
    StructuredResult,
    Usage,
)

log = logging.getLogger(__name__)

API_HOST = "api.anthropic.com"

_JSON_ONLY_NOTE = (
    "Respond with ONLY a single JSON object matching this JSON schema, no prose, no code fences:\n"
)


def _map_error(exc: Exception) -> ProviderError:
    """Map SDK exceptions to key-free ProviderError kinds (most specific first)."""
    request_id = None
    status = getattr(exc, "status_code", None)
    resp = getattr(exc, "response", None)
    if resp is not None:
        try:
            request_id = resp.headers.get("request-id")
        except Exception:
            request_id = None
    if isinstance(exc, anthropic.AuthenticationError):
        kind = "invalid_key"
    elif isinstance(exc, anthropic.PermissionDeniedError):
        kind = "permission"
    elif isinstance(exc, anthropic.NotFoundError):
        kind = "model_not_found"
    elif isinstance(exc, anthropic.RateLimitError):
        kind = "rate_limited"
    elif isinstance(exc, anthropic.BadRequestError):
        # Out-of-credits arrives as a 400 whose message mentions the credit
        # balance. We inspect the text but never log or display it.
        msg = str(getattr(exc, "message", "") or "").lower()
        kind = "no_credits" if "credit" in msg or "billing" in msg else "bad_request"
    elif isinstance(exc, anthropic.APITimeoutError):
        kind = "network"
    elif isinstance(exc, anthropic.APIConnectionError):
        kind = "network"
    elif isinstance(exc, anthropic.APIStatusError):
        kind = "outage" if (status or 0) >= 500 else "unknown"
    else:
        kind = "unknown"
    return ProviderError(kind, status=status, request_id=request_id)


def _is_format_unsupported(exc: Exception) -> bool:
    if not isinstance(exc, anthropic.BadRequestError):
        return False
    msg = str(getattr(exc, "message", "") or "").lower()
    return "output_config" in msg or "json_schema" in msg or "format" in msg


def _extract_json(text: str) -> dict | None:
    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, capabilities: Capabilities | None = None,
                 client: anthropic.Anthropic | None = None):
        super().__init__(model, capabilities or Capabilities(vision=True, structured_output=True, streaming=True))
        # max_retries: the SDK retries 408/409/429/5xx and connection errors.
        self._client = client or anthropic.Anthropic(api_key=api_key, max_retries=2, timeout=60.0)

    # -------------------------------------------------------------- calls

    def _system(self, blocks: list[str]) -> list[dict]:
        # Every system block is stable for the life of a problem (system prompt,
        # then problem context), so each gets a breakpoint. API max is 4.
        out = []
        for i, text in enumerate(blocks):
            block: dict = {"type": "text", "text": text}
            if i < 4:
                block["cache_control"] = {"type": "ephemeral"}
            out.append(block)
        return out

    def structured(self, req: StructuredRequest) -> StructuredResult:
        use_native = self.capabilities.structured_output
        system_blocks = list(req.system_blocks)
        if not use_native:
            system_blocks.append(_JSON_ONLY_NOTE + json.dumps(req.schema, sort_keys=True))
        kwargs: dict = {
            "model": self.model,
            "max_tokens": req.max_tokens,
            "system": self._system(system_blocks),
            "messages": req.messages,
        }
        if use_native:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": req.schema}}
        try:
            resp = self._client.messages.create(**kwargs)
        except Exception as exc:  # noqa: BLE001 - mapped below
            err = _map_error(exc)
            log.warning("anthropic call failed: kind=%s status=%s request_id=%s purpose=%s",
                        err.kind, err.status, err.request_id, req.purpose)
            raise err from None

        usage = Usage(
            input_tokens=getattr(resp.usage, "input_tokens", 0) or 0,
            output_tokens=getattr(resp.usage, "output_tokens", 0) or 0,
            cache_read_tokens=getattr(resp.usage, "cache_read_input_tokens", 0) or 0,
            cache_write_tokens=getattr(resp.usage, "cache_creation_input_tokens", 0) or 0,
        )
        if resp.stop_reason == "refusal":
            log.info("anthropic refusal: purpose=%s", req.purpose)
            return StructuredResult(data=None, usage=usage, malformed=True)
        text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
        data = _extract_json(text)
        return StructuredResult(
            data=data,
            usage=usage,
            malformed=data is None,
            truncated=resp.stop_reason == "max_tokens",
        )

    # -------------------------------------------------------------- probe

    def probe(self) -> Capabilities:
        """Test the key and detect capabilities in one tiny call (§11.2).

        The first attempt uses both structured output and a tiny 16x16 image.
        If the model rejects one of them (400), that capability is turned off
        and the call is retried without it. Key/network failures raise
        ProviderError. Costs a few dozen tokens.
        """
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}},
                  "required": ["ok"], "additionalProperties": False}
        caps = Capabilities(vision=True, structured_output=True, streaming=True)
        for _ in range(3):
            content: list[dict] | str
            if caps.vision:
                content = [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                 "data": base64.standard_b64encode(_probe_png()).decode()}},
                    {"type": "text", "text": "Reply with ok=true."},
                ]
            else:
                content = "Reply with ok=true."
            kwargs: dict = {"model": self.model, "max_tokens": 16,
                            "messages": [{"role": "user", "content": content}]}
            if caps.structured_output:
                kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
            try:
                self._client.messages.create(**kwargs)
                break
            except Exception as exc:  # noqa: BLE001
                if caps.vision and _is_image_unsupported(exc):
                    caps.vision = False
                elif caps.structured_output and _is_format_unsupported(exc):
                    caps.structured_output = False
                else:
                    raise _map_error(exc) from None
        else:
            raise ProviderError("missing_capability")
        self.capabilities = caps
        return caps


def _is_image_unsupported(exc: Exception) -> bool:
    if not isinstance(exc, anthropic.BadRequestError):
        return False
    msg = str(getattr(exc, "message", "") or "").lower()
    return "image" in msg or "vision" in msg


def _probe_png() -> bytes:
    """A 16x16 white PNG, built in code (no binary files in the repo)."""
    import struct
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    w = h = 16
    raw = b"".join(b"\x00" + b"\xff\xff\xff" * w for _ in range(h))  # filter byte + RGB row
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))
