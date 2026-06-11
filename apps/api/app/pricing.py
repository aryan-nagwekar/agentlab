"""Deterministic, local model pricing.

No external calls and no real provider integration — v0.6 uses mock providers
only. Prices are USD per 1,000,000 tokens. BYOK / a real model gateway is v0.7.
"""
from __future__ import annotations

from typing import Any

# model_name -> {input_per_1m, output_per_1m}. Mock providers only.
MODEL_PRICING: dict[str, dict[str, float]] = {
    "mock:gpt-4.1": {"input_per_1m": 2.00, "output_per_1m": 8.00},
    "mock:claude-sonnet": {"input_per_1m": 3.00, "output_per_1m": 15.00},
    "mock:gemini-pro": {"input_per_1m": 1.25, "output_per_1m": 5.00},
    "mock:local-ollama": {"input_per_1m": 0.00, "output_per_1m": 0.00},
}


def provider_of(model_name: str | None) -> str:
    if not model_name:
        return "unknown"
    return model_name.split(":", 1)[0] if ":" in model_name else "unknown"


def estimate_cost(
    model_name: str | None, input_tokens: int, output_tokens: int
) -> tuple[float | None, str]:
    """Returns (estimated_cost_usd, pricing_status).

    pricing_status is "ok" for a known model, "unknown" otherwise (cost None).
    """
    if not model_name or model_name not in MODEL_PRICING:
        return None, "unknown"
    rates = MODEL_PRICING[model_name]
    cost = (
        (input_tokens or 0) * rates["input_per_1m"]
        + (output_tokens or 0) * rates["output_per_1m"]
    ) / 1_000_000
    return round(cost, 6), "ok"


def pricing_table() -> list[dict[str, Any]]:
    return [
        {
            "model_name": name,
            "provider": provider_of(name),
            "input_per_1m": rates["input_per_1m"],
            "output_per_1m": rates["output_per_1m"],
        }
        for name, rates in MODEL_PRICING.items()
    ]
