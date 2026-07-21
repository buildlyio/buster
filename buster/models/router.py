"""Local-first model router.

Routing order (spec):
  1. Suitable model on the current device
  2. More capable model on the current device
  3. Trusted model on the local network
  4. User-controlled remote model service
  5. Approved commercial/hosted provider

Remote inference is NOT chosen just because it is faster. It is only considered
when no suitable local model exists, the machine lacks resources, the local
model lacks a capability, context exceeds local capacity, the user requests it,
or workspace policy allows fallback.
"""

from __future__ import annotations

from dataclasses import dataclass

from buster.config.settings import BusterConfig
from buster.models.disabled import DisabledProvider
from buster.models.ollama import OllamaProvider
from buster.models.provider import InferenceLocation, ModelInfo, ModelProvider


@dataclass
class RouteDecision:
    provider: ModelProvider
    model: str
    location: InferenceLocation
    external_data_shared: bool
    reason: str


class ModelRouter:
    def __init__(self, config: BusterConfig) -> None:
        self.config = config
        self._local = OllamaProvider(config.inference.ollama_url, location="device")
        self._lan = [
            OllamaProvider(url, location="lan")
            for url in config.inference.lan_ollama_urls
        ]

    async def local_provider(self) -> OllamaProvider:
        return self._local

    async def available_models(self) -> list[ModelInfo]:
        models: list[ModelInfo] = []
        try:
            models += await self._local.list_models()
        except Exception:  # noqa: BLE001
            pass
        for lan in self._lan:
            try:
                models += await lan.list_models()
            except Exception:  # noqa: BLE001
                pass
        return models

    def _pick_default(self, models: list[ModelInfo]) -> str | None:
        if self.config.inference.default_model:
            wanted = self.config.inference.default_model
            for m in models:
                if m.name == wanted:
                    return wanted
        # Prefer a general chat model over embedding-only models.
        for m in models:
            if "embed" not in m.name.lower():
                return m.name
        return models[0].name if models else None

    async def route(
        self,
        *,
        model: str | None = None,
        needs_capability: str | None = None,
        estimated_tokens: int = 0,
    ) -> RouteDecision:
        """Choose a provider+model for a chat task."""
        policy = self.config.inference.policy

        # 1 & 2: current device.
        local_ok = await self._local.health()
        if local_ok.reachable:
            local_models = await self._local.list_models()
            chosen = model if model and _has(local_models, model) else self._pick_default(local_models)
            if chosen:
                return RouteDecision(
                    provider=self._local,
                    model=chosen,
                    location="device",
                    external_data_shared=False,
                    reason="Suitable local model on this device.",
                )

        # 3: trusted LAN model (only if allowed by policy).
        if policy in ("local_first_auto_lan", "no_restriction", "local_first_ask_external"):
            for lan in self._lan:
                lan_ok = await lan.health()
                if lan_ok.reachable:
                    lan_models = await lan.list_models()
                    chosen = model if model and _has(lan_models, model) else self._pick_default(lan_models)
                    if chosen:
                        return RouteDecision(
                            provider=lan,
                            model=chosen,
                            location="lan",
                            external_data_shared=False,
                            reason="No suitable local model; using trusted LAN Ollama.",
                        )

        # 4 & 5: remote — deferred in Phase 1 (interface only). Never auto-used
        # unless policy explicitly permits.
        # Fall back to a clear disabled response.
        return RouteDecision(
            provider=DisabledProvider(),
            model="none",
            location="unknown",
            external_data_shared=False,
            reason="No local or trusted LAN model available; remote inference not enabled.",
        )


def _has(models: list[ModelInfo], name: str) -> bool:
    return any(m.name == name for m in models)
