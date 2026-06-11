"""Model gateway core types and the provider interface.

Security: API keys live only in process memory (loaded from the environment).
They are never stored, never returned to clients, never logged, and never put
into error messages. The only key information that leaves the server is a
redacted hint produced by ``redact_key``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal


def redact_key(key: str | None) -> str | None:
    """Turn a secret into a safe display hint, e.g. 'sk-...wxyz'. Never returns
    enough characters to be useful."""
    if not key:
        return None
    cleaned = key.strip()
    if len(cleaned) <= 6:
        return "***"
    prefix = cleaned[:3]
    suffix = cleaned[-4:]
    return f"{prefix}...{suffix}"


@dataclass
class ModelRequest:
    provider: str
    model_name: str
    prompt: str
    agent_id: str | None = None
    run_id: str | None = None
    project_id: str | None = None
    system_prompt: str | None = None
    temperature: float = 0.2
    max_tokens: int = 1000
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelResponse:
    provider: str
    model_name: str
    output_text: str
    latency_ms: int
    status: Literal["completed", "failed"] = "completed"
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    estimated_cost_usd: float | None = None
    error_message: str | None = None
    raw_usage: dict[str, Any] = field(default_factory=dict)


# Provider health states.
HEALTH_AVAILABLE = "available"
HEALTH_NOT_CONFIGURED = "not_configured"
HEALTH_UNAVAILABLE = "unavailable"
HEALTH_ERROR = "error"


@dataclass
class ProviderHealth:
    name: str
    status: str
    configured: bool
    detail: str | None = None
    key_redacted: str | None = None


class ModelProvider:
    """Base class for model providers. Subclasses implement complete + health."""

    name: str = "base"
    #: Whether this provider needs an API key to be considered configured.
    requires_key: bool = True

    def models(self) -> list[str]:
        return []

    @property
    def configured(self) -> bool:
        return True

    def key_redacted(self) -> str | None:
        return None

    async def complete(self, request: ModelRequest) -> ModelResponse:  # pragma: no cover - abstract
        raise NotImplementedError

    async def health_check(self) -> ProviderHealth:  # pragma: no cover - abstract
        raise NotImplementedError
