"""Mock provider — the keyless default for demos and tests.

Deterministic output and token usage (seeded by the prompt), configurable
latency and failure simulation. Never makes a network call. Models match the
pricing table so cost attribution flows through the v0.6 costing engine.
"""
from __future__ import annotations

import asyncio
import hashlib

from ..base import (
    HEALTH_AVAILABLE,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderHealth,
)

MOCK_MODELS = [
    "mock:claude-sonnet",
    "mock:gpt-4.1",
    "mock:gemini-pro",
    "mock:local-ollama",
]


def _seeded_int(text: str, low: int, high: int) -> int:
    digest = int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)
    return low + (digest % (high - low + 1))


class MockProvider(ModelProvider):
    name = "mock"
    requires_key = False

    def models(self) -> list[str]:
        return list(MOCK_MODELS)

    @property
    def configured(self) -> bool:
        return True

    async def complete(self, request: ModelRequest) -> ModelResponse:
        meta = request.metadata or {}
        # Latency: caller may pin it; otherwise deterministic from the prompt.
        # We optionally sleep a tiny, bounded amount so demos feel alive without
        # slowing tests (sleep is skipped when simulate_latency is false).
        latency_ms = int(meta.get("latency_ms") or _seeded_int(request.prompt, 120, 900))
        if meta.get("simulate_latency"):
            await asyncio.sleep(min(latency_ms, 1500) / 1000)

        if meta.get("simulate_failure") or request.model_name.endswith(":fail"):
            return ModelResponse(
                provider=self.name,
                model_name=request.model_name,
                output_text="",
                latency_ms=latency_ms,
                status="failed",
                input_tokens=_seeded_int(request.prompt, 50, 400),
                output_tokens=0,
                total_tokens=_seeded_int(request.prompt, 50, 400),
                error_message="Simulated provider failure (mock)",
            )

        input_tokens = max(1, len(request.prompt.split()) * 3 + _seeded_int(request.prompt, 20, 200))
        output_tokens = _seeded_int(request.prompt + "out", 40, 300)
        output_text = (
            f"[{request.model_name}] Mock completion for: "
            f"{request.prompt[:80]}{'…' if len(request.prompt) > 80 else ''}"
        )
        return ModelResponse(
            provider=self.name,
            model_name=request.model_name,
            output_text=output_text,
            latency_ms=latency_ms,
            status="completed",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            # Cost is left to the costing/pricing engine (mock: models are priced).
            raw_usage={"simulated": True},
        )

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(
            name=self.name,
            status=HEALTH_AVAILABLE,
            configured=True,
            detail="Keyless mock provider — always available.",
        )
