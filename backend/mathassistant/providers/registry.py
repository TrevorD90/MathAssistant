"""Provider/model registry and the tested list (spec §11.2).

A model is "tested" once it passes the §14 acceptance tests against the live
API (`backend/tests/live/`). Untested models are allowed behind a warning.

[DECISION: both Anthropic models start as untested. Neither has been run
through the live acceptance suite yet (it needs a real key). Flip `tested`
after `pytest backend/tests/live` passes for that model.]
"""

from __future__ import annotations

from dataclasses import dataclass

from .anthropic_provider import AnthropicProvider
from .base import Capabilities, LLMProvider

UNTESTED_WARNING = (
    "Untested model. It may reveal answers, misread photos, or break the display box. "
    "Answers are still checked for leaks."
)


@dataclass(frozen=True)
class ModelInfo:
    id: str
    label: str
    tested: bool
    note: str = ""


@dataclass(frozen=True)
class ProviderInfo:
    id: str
    label: str
    key_url: str
    models: tuple[ModelInfo, ...]


PROVIDERS: dict[str, ProviderInfo] = {
    "anthropic": ProviderInfo(
        id="anthropic",
        label="Anthropic (Claude)",
        key_url="https://console.anthropic.com/settings/keys",
        models=(
            ModelInfo("claude-haiku-4-5", "Claude Haiku 4.5 (lowest cost)", tested=False,
                      note="Default. $1 / $5 per million tokens in/out."),
            ModelInfo("claude-sonnet-5", "Claude Sonnet 5", tested=False,
                      note="Stronger explanations. $2 / $10 per million tokens in/out."),
        ),
    ),
}

DEFAULT_PROVIDER = "anthropic"
DEFAULT_MODEL = "claude-haiku-4-5"


def model_info(provider: str, model: str) -> ModelInfo | None:
    p = PROVIDERS.get(provider)
    if not p:
        return None
    return next((m for m in p.models if m.id == model), None)


def is_tested(provider: str, model: str) -> bool:
    info = model_info(provider, model)
    return bool(info and info.tested)


def create_provider(provider: str, model: str, api_key: str,
                    capabilities: Capabilities | None = None) -> LLMProvider:
    if provider == "anthropic":
        return AnthropicProvider(api_key=api_key, model=model, capabilities=capabilities)
    raise ValueError(f"unknown provider {provider!r}")


def catalog() -> list[dict]:
    """Serializable provider/model list for the Settings screen."""
    return [
        {
            "id": p.id,
            "label": p.label,
            "key_url": p.key_url,
            "models": [{"id": m.id, "label": m.label, "tested": m.tested, "note": m.note} for m in p.models],
        }
        for p in PROVIDERS.values()
    ]
