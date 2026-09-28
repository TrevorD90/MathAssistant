"""Scripted provider for tests and offline development.

Counts every call (the §14 cost tests assert on `calls`) and can be forced to
leak (the §14 guardrail test). Never makes network calls.
"""

from __future__ import annotations

from typing import Callable

from .base import Capabilities, LLMProvider, ProviderError, StructuredRequest, StructuredResult, Usage

Responder = Callable[[StructuredRequest], dict | None]


class FakeProvider(LLMProvider):
    name = "fake"

    def __init__(self, responder: Responder | None = None, model: str = "fake-model",
                 capabilities: Capabilities | None = None, fail_with: str | None = None):
        super().__init__(model, capabilities or Capabilities(vision=True, structured_output=True))
        self.responder = responder or (lambda req: None)
        self.fail_with = fail_with
        self.calls: list[StructuredRequest] = []

    @property
    def call_count(self) -> int:
        return len(self.calls)

    def structured(self, req: StructuredRequest) -> StructuredResult:
        self.calls.append(req)
        if self.fail_with:
            raise ProviderError(self.fail_with)
        data = self.responder(req)
        return StructuredResult(
            data=data,
            usage=Usage(input_tokens=100, output_tokens=40),
            malformed=data is None,
        )

    def probe(self) -> Capabilities:
        if self.fail_with:
            raise ProviderError(self.fail_with)
        return self.capabilities
