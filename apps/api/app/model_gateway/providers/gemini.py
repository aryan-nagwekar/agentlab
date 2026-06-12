"""Google Gemini provider (generateContent API).

The API key is held only in memory and never logged or returned. Tests never
require a real key — without one the provider reports ``not_configured``.
Gemini's usage metadata is read defensively: if a field is missing or shaped
differently, token counts come back as None rather than raising.
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

# Conservative, easy-to-update list.
DEFAULT_MODELS = [
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-2.0-flash",
    "gemini-2.5-flash",
]


class GeminiProvider(ModelProvider):
    name = "gemini"
    requires_key = True

    def __init__(
        self,
        api_key: str | None,
        *,
        base_url: str = "https://generativelanguage.googleapis.com/v1beta",
        models: list[str] | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._models = models or list(DEFAULT_MODELS)

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
                error_message="gemini provider is not configured (no API key).",
            )
        body: dict = {
            "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
            "generationConfig": {
                "temperature": request.temperature,
                "maxOutputTokens": request.max_tokens,
            },
        }
        if request.system_prompt:
            body["systemInstruction"] = {"parts": [{"text": request.system_prompt}]}
        # The key travels as a query param per the Gemini REST API. It is never
        # logged and the HTTP helper omits the URL from error messages.
        url = f"{self._base_url}/models/{request.model_name}:generateContent?key={self._api_key}"
        started = time.perf_counter()
        try:
            payload, _status, latency_ms = await post_json(
                url, headers={"Content-Type": "application/json"}, body=body
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

        text = _extract_text(payload)
        usage = payload.get("usageMetadata") or {}
        input_tokens = _as_int_or_none(usage.get("promptTokenCount"))
        output_tokens = _as_int_or_none(usage.get("candidatesTokenCount"))
        total = _as_int_or_none(usage.get("totalTokenCount"))
        if total is None and input_tokens is not None and output_tokens is not None:
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
                detail="Set GEMINI_API_KEY (or GOOGLE_API_KEY) to enable this provider.",
            )
        return ProviderHealth(
            name=self.name,
            status=HEALTH_AVAILABLE,
            configured=True,
            detail="Configured.",
            key_redacted=redact_key(self._api_key),
        )


def _as_int_or_none(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _extract_text(payload: dict) -> str:
    """Pull the text out of the first candidate, tolerating shape changes."""
    candidates = payload.get("candidates") or []
    if not candidates:
        return ""
    parts = ((candidates[0] or {}).get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if isinstance(p, dict))
