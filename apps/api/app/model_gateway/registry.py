"""Provider registry — builds the available providers from Settings.

Keys come from the environment (via Settings), optionally overlaid by the
local gitignored secrets file (v0.9.1 — the most recent explicit user action
wins). They are kept in memory only; construction never logs or echoes a key.
"""
from __future__ import annotations

from ..config import Settings
from .base import ModelProvider
from .providers.anthropic import AnthropicProvider
from .providers.gemini import GeminiProvider
from .providers.mock import MockProvider
from .providers.ollama import OllamaProvider
from .providers.openai_compatible import OpenAICompatibleProvider
from .secrets_store import load_secrets


class ProviderRegistry:
    def __init__(self, providers: list[ModelProvider]) -> None:
        self._providers = {p.name: p for p in providers}

    def names(self) -> list[str]:
        return list(self._providers)

    def get(self, name: str) -> ModelProvider | None:
        return self._providers.get(name)

    def all(self) -> list[ModelProvider]:
        return list(self._providers.values())


def build_registry(settings: Settings) -> ProviderRegistry:
    secrets = load_secrets(settings.secrets_file)

    def value(provider: str, key: str, env_default: str) -> str:
        return secrets.get(provider, {}).get(key) or env_default

    providers: list[ModelProvider] = [
        MockProvider(),
        OpenAICompatibleProvider(
            value("openai", "api_key", settings.openai_api_key) or None,
            base_url=value("openai", "base_url", settings.openai_base_url),
            name="openai",
        ),
        AnthropicProvider(value("anthropic", "api_key", settings.anthropic_api_key) or None),
        GeminiProvider(
            value("gemini", "api_key", settings.gemini_api_key) or None,
            base_url=value("gemini", "base_url", settings.gemini_base_url),
        ),
        OllamaProvider(value("ollama", "base_url", settings.ollama_base_url)),
    ]
    # OpenRouter is just an OpenAI-compatible endpoint; expose it only if keyed.
    if settings.openrouter_api_key:
        providers.append(
            OpenAICompatibleProvider(
                settings.openrouter_api_key,
                base_url="https://openrouter.ai/api/v1",
                name="openrouter",
                models=["openrouter/auto"],
            )
        )
    return ProviderRegistry(providers)
