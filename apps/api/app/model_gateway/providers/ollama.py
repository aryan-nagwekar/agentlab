"""Ollama local-model provider.

No API key — configured by a base URL (default http://localhost:11434). If
Ollama is not running the health check reports ``unavailable`` rather than
failing the app.
"""
from __future__ import annotations

import time

from ..base import (
    HEALTH_AVAILABLE,
    HEALTH_UNAVAILABLE,
    ModelProvider,
    ModelRequest,
    ModelResponse,
    ProviderHealth,
)
from ._http import HttpError, get_status, post_json


class OllamaProvider(ModelProvider):
    name = "ollama"
    requires_key = False

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        *,
        models: list[str] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._models = models or ["llama3.1", "qwen2.5", "mistral"]

    def models(self) -> list[str]:
        return list(self._models)

    @property
    def configured(self) -> bool:
        return True  # local; configured by URL, no key

    async def complete(self, request: ModelRequest) -> ModelResponse:
        body = {
            "model": request.model_name,
            "prompt": request.prompt,
            "system": request.system_prompt or "",
            "stream": False,
            "options": {"temperature": request.temperature, "num_predict": request.max_tokens},
        }
        started = time.perf_counter()
        try:
            # Local models can take minutes to generate a longer page; give
            # completions a generous timeout (the default 30s is for fast APIs).
            payload, _status, latency_ms = await post_json(
                f"{self._base_url}/api/generate",
                headers={"Content-Type": "application/json"},
                body=body,
                timeout=300.0,
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
        input_tokens = payload.get("prompt_eval_count")
        output_tokens = payload.get("eval_count")
        total = None
        if input_tokens is not None and output_tokens is not None:
            total = input_tokens + output_tokens
        return ModelResponse(
            provider=self.name,
            model_name=request.model_name,
            output_text=payload.get("response", ""),
            latency_ms=latency_ms,
            status="completed",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total,
            # Local models are free; cost stays 0 unless priced.
            estimated_cost_usd=0.0,
            raw_usage={k: payload.get(k) for k in ("prompt_eval_count", "eval_count") if k in payload},
        )

    async def health_check(self) -> ProviderHealth:
        try:
            await get_status(f"{self._base_url}/api/tags", timeout=2.0)
        except Exception:  # noqa: BLE001 - any failure means Ollama isn't reachable
            return ProviderHealth(
                name=self.name,
                status=HEALTH_UNAVAILABLE,
                configured=True,
                detail=(
                    f"No Ollama server at {self._base_url}. "
                    "Start it with `ollama serve` (then `ollama pull llama3.2`), "
                    "or point OLLAMA_BASE_URL at your server — Docker users: "
                    "http://host.docker.internal:11434."
                ),
            )
        return ProviderHealth(
            name=self.name,
            status=HEALTH_AVAILABLE,
            configured=True,
            detail=f"Reachable at {self._base_url}.",
        )
