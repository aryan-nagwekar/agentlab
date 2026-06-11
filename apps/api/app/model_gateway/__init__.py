"""AgentLab model gateway: a local-first provider abstraction with safe BYOK.

API keys are loaded from the environment and kept only in memory — never
stored, returned to clients, or logged. The mock provider works without keys.
"""
from .base import ModelRequest, ModelResponse, ProviderHealth, redact_key
from .registry import ProviderRegistry, build_registry
from .telemetry import build_model_events

__all__ = [
    "ModelRequest",
    "ModelResponse",
    "ProviderHealth",
    "ProviderRegistry",
    "build_registry",
    "build_model_events",
    "redact_key",
]
