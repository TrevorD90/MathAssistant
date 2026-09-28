"""Provider adapter interface (spec §11.2).

Every provider implements `LLMProvider`. Features are gated on declared
`Capabilities`; the leak guard and SymPy checks apply regardless of provider.

Phase 1 uses only `structured()` (intake + turns). `vision_extract()` is part
of the interface for Phase 2; streaming chat is declared as a capability but
not used in Phase 1 (replies are buffered so the leak guard runs before
anything is shown — see CLAUDE.md decision log).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Capabilities:
    vision: bool = False
    structured_output: bool = False   # native JSON-schema constrained output
    streaming: bool = False


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0

    def add(self, other: "Usage") -> "Usage":
        return Usage(
            self.input_tokens + other.input_tokens,
            self.output_tokens + other.output_tokens,
            self.cache_read_tokens + other.cache_read_tokens,
            self.cache_write_tokens + other.cache_write_tokens,
        )

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_read_tokens + self.cache_write_tokens


@dataclass
class StructuredRequest:
    """One AI call. `system_blocks` are ordered stable -> less stable (cacheable prefix)."""

    system_blocks: list[str]
    messages: list[dict]            # [{"role": "user"|"assistant", "content": str}]
    schema: dict
    max_tokens: int
    purpose: str = "turn"           # "intake" | "turn" | "probe" (for counting/logging)


@dataclass
class StructuredResult:
    data: dict | None               # parsed JSON, or None if malformed
    usage: Usage = field(default_factory=Usage)
    malformed: bool = False
    truncated: bool = False


# Error kinds with fixed, key-free user messages (§11.3). Provider error text
# is never shown or logged verbatim.
ERROR_MESSAGES = {
    "invalid_key": "The API key was rejected. It may be mistyped, expired, or revoked. Check it in Settings.",
    "permission": "This API key doesn't have permission to use the selected model.",
    "no_credits": "Your AI provider account is out of credits. Add credits with the provider, then try again.",
    "rate_limited": "The AI provider is rate-limiting requests. Wait a minute and try again.",
    "outage": "The AI provider is having problems right now. Try again in a few minutes.",
    "network": "Couldn't reach the AI provider. Check your internet connection.",
    "model_not_found": "The selected model wasn't found. Pick a different model in Settings.",
    "missing_capability": "The selected model doesn't support a feature this needs. Pick a tested model in Settings.",
    "no_key": "No API key is set. Add one in Settings.",
    "keystore_unavailable": "Your computer's credential store isn't available, so the key can't be stored safely.",
    "bad_request": "The AI provider rejected the request.",
    "unknown": "Something went wrong talking to the AI provider.",
}


class ProviderError(Exception):
    def __init__(self, kind: str, *, status: int | None = None, request_id: str | None = None):
        self.kind = kind if kind in ERROR_MESSAGES else "unknown"
        self.status = status
        self.request_id = request_id
        super().__init__(self.kind)

    @property
    def user_message(self) -> str:
        return ERROR_MESSAGES[self.kind]


class LLMProvider(ABC):
    name: str = "base"

    def __init__(self, model: str, capabilities: Capabilities | None = None):
        self.model = model
        self.capabilities = capabilities or Capabilities()

    @abstractmethod
    def structured(self, req: StructuredRequest) -> StructuredResult:
        """One call returning JSON that matches `req.schema` (or malformed=True)."""

    @abstractmethod
    def probe(self) -> Capabilities:
        """Test the key with a tiny call and detect capabilities. Raises ProviderError."""

    def vision_extract(self, image_bytes: bytes, media_type: str) -> str:  # pragma: no cover - Phase 2
        raise ProviderError("missing_capability")
