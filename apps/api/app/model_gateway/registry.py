"""Provider registry — builds the available providers from Settings.

Keys are read from the environment (via Settings) once and kept in memory.
Construction never logs or echoes a key.
"""
from __future__ import annotations

from ..config import Settings
from .base import ModelProvider
from .providers.anthropic import AnthropicProvider
from .providers.gemini import GeminiProvider
from .providers.mock import MockProvider
from .providers.ollama import OllamaProvider
from .providers.openai_compatible import OpenAICompatibleProvider


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
    providers: list[ModelProvider] = [
        MockProvider(),
        OpenAICompatibleProvider(
            settings.openai_api_key or None,
            base_url=settings.openai_base_url,
            name="openai",
        ),
        AnthropicProvider(settings.anthropic_api_key or None),
        GeminiProvider(settings.gemini_api_key or None, base_url=settings.gemini_base_url),
        OllamaProvider(settings.ollama_base_url),
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
