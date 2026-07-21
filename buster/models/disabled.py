"""Provider used when no LLM is available.

Buster stays useful without a model: deterministic features (diagnostics,
discovery, alerts, cache, memory search) run regardless. Chat calls return a
clear, honest message instead of failing.
"""

from __future__ import annotations

from buster.models.provider import (
    ChatRequest,
    ChatResponse,
    ModelCapabilities,
    ModelInfo,
    ProviderHealth,
)

_MSG = (
    "No language model is currently available. Deterministic features "
    "(system checks, network checks, discovery, alerts, memory search, cache "
    "management) still work. Install Ollama and pull a model to enable chat."
)


class DisabledProvider:
    name = "disabled"

    async def health(self) -> ProviderHealth:
        return ProviderHealth(
            provider=self.name, reachable=False, location="unknown", detail=_MSG
        )

    async def list_models(self) -> list[ModelInfo]:
        return []

    async def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities()

    async def chat(self, request: ChatRequest) -> ChatResponse:
        return ChatResponse(
            model="none",
            provider=self.name,
            inference_location="unknown",
            content=_MSG,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[] for _ in texts]
