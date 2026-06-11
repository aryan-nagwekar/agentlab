"""OpenAI-compatible chat completions provider.

Works against the OpenAI API or any compatible endpoint (OpenRouter, etc.) via
a configurable base URL. The API key is held only in memory and never logged or
returned. Tests never require a real key — without one the provider reports
``not_configured``.
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


class OpenAICompatibleProvider(ModelProvider):
    name = "openai"
    requires_key = True

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://api.openai.com/v1",
        name: str = "openai",
        models: list[str] | None = None,
    ) -> None:
        self.name = name
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._models = models or ["gpt-4.1", "gpt-4.1-mini", "gpt-4o"]

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
                error_message=f"{self.name} provider is not configured (no API key).",
            )
        messages = []
        if request.system_prompt:
            messages.append({"role": "system", "content": request.system_prompt})
        messages.append({"role": "user", "content": request.prompt})
        body = {
            "model": request.model_name,
            "messages": messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        started = time.perf_counter()
        try:
            payload, _status, latency_ms = await post_json(
                f"{self._base_url}/chat/completions", headers=headers, body=body
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
        usage = payload.get("usage", {})
        text = ""
        choices = payload.get("choices") or []
        if choices:
            text = (choices[0].get("message") or {}).get("content", "")
        input_tokens = usage.get("prompt_tokens")
        output_tokens = usage.get("completion_tokens")
        return ModelResponse(
            provider=self.name,
            model_name=request.model_name,
            output_text=text,
            latency_ms=latency_ms,
            status="completed",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=usage.get("total_tokens"),
            raw_usage=usage,
        )

    async def health_check(self) -> ProviderHealth:
        if not self._api_key:
            return ProviderHealth(
                name=self.name,
                status=HEALTH_NOT_CONFIGURED,
                configured=False,
                detail="Set OPENAI_API_KEY to enable this provider.",
            )
        # We do not spend a real request on health; a configured key is reported
        # as available. A live test is available via the test-call endpoint.
        return ProviderHealth(
            name=self.name,
            status=HEALTH_AVAILABLE,
            configured=True,
            detail=f"Configured ({self._base_url}).",
            key_redacted=redact_key(self._api_key),
        )
