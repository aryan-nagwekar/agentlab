"""Anthropic / Claude messages provider.

The API key is held only in memory and never logged or returned. Tests never
require a real key — without one the provider reports ``not_configured``.
"""
from __future__ import annotations

import time

from ..base import (
    HEALTH_AVAILABLE,
    HEALTH_NOT_CONFIGURED,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderHealth,
    redact_key,
)
from ._http import HttpError, post_json

ANTHROPIC_VERSION = "2023-06-01"


class AnthropicProvider(ModelProvider):
    name = "anthropic"
    requires_key = True

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://api.anthropic.com/v1",
        models: list[str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._models = models or ["claude-sonnet-4-6", "claude-opus-4-8", "claude-haiku-4-5"]

    def models(self) -> list[str]:
        return list(self._models)

    @property
    def configured(self) -> bool:
        return bool(self._api_key)

    def key_redacted(self) -> str | None:
        return redact_key(self._api_key)

    async def complete(self, request: ModelRequest) -> ModelResponse:
        if not self._api_key:
            return ModelResponse(
                provider=self.name,
                model_name=request.model_name,
                output_text="",
                latency_ms=0,
                status="failed",
                error_message="anthropic provider is not configured (no API key).",
            )
        body = {
            "model": request.model_name,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system_prompt:
            body["system"] = request.system_prompt
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": ANTHROPIC_VERSION,
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        try:
            payload, _status, latency_ms = await post_json(
                f"{self._base_url}/messages", headers=headers, body=body
            )
        except HttpError as exc:
            return ModelResponse(
                provider=self.name,
                model_name=request.model_name,
                output_text="",
                latency_ms=int((time.perf_counter() - started) * 1000),
                status="failed",
                error_message=str(exc),
            )
        blocks = payload.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if isinstance(b, dict))
        usage = payload.get("usage", {})
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total = None
        if input_tokens is not None and output_tokens is not None:
            total = input_tokens + output_tokens
        return ModelResponse(
            provider=self.name,
            model_name=request.model_name,
            output_text=text,
            latency_ms=latency_ms,
            status="completed",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            raw_usage=usage,
        )

    async def health_check(self) -> ProviderHealth:
        if not self._api_key:
            return ProviderHealth(
                name=self.name,
                status=HEALTH_NOT_CONFIGURED,
                configured=False,
                detail="Set ANTHROPIC_API_KEY to enable this provider.",
            )
        return ProviderHealth(
            name=self.name,
            status=HEALTH_AVAILABLE,
            configured=True,
            detail="Configured.",
            key_redacted=redact_key(self._api_key),
        )
