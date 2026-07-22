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
from buster.models.lmstudio import OpenAICompatibleProvider
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
        inf = config.inference
        self._local = OllamaProvider(inf.ollama_url, location="device")

        # Device-tier providers (this machine): local Ollama + local LM Studio.
        self._device: list = [self._local]
        for url in inf.lmstudio_urls:
            loc = "device" if ("127.0.0.1" in url or "localhost" in url) else "lan"
            if loc == "device":
                self._device.append(
                    OpenAICompatibleProvider(url, location="device", name="lmstudio")
                )

        # LAN-tier providers: trusted LAN Ollama + non-local LM Studio endpoints.
        self._lan: list = [OllamaProvider(url, location="lan") for url in inf.lan_ollama_urls]
        for url in inf.lmstudio_urls:
            if not ("127.0.0.1" in url or "localhost" in url):
                self._lan.append(OpenAICompatibleProvider(url, location="lan", name="lmstudio"))

        # Gated remote provider (opt-in; sends data off-network).
        self._remote = None
        if inf.remote.enabled and inf.remote.base_url:
            self._remote = OpenAICompatibleProvider(
                inf.remote.base_url, location="remote",
                api_key=inf.remote.api_key, name=inf.remote.name or "remote",
            )

    async def local_provider(self) -> OllamaProvider:
        return self._local

    async def available_models(self, use_cache: bool = True) -> list[ModelInfo]:
        # Model inventory changes rarely but costs a network round-trip per
        # provider. Cache it briefly so /status and repeated routes stay snappy.
        from buster.cache import get_cache

        cache = get_cache()
        key = "router:available_models"
        if use_cache:
            hit = cache.mem_get(key)
            if hit is not None:
                return [ModelInfo.model_validate(m) for m in hit]

        models: list[ModelInfo] = []
        for prov in [*self._device, *self._lan]:
            try:
                models += await prov.list_models()
            except Exception:  # noqa: BLE001
                pass
        cache.mem_set(key, [m.model_dump() for m in models], ttl=30)
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

        # 0: honor an explicitly requested/configured model wherever it lives.
        # Without this, the device tier (checked first) could win with a
        # different model than the user's configured default (which may be on
        # the LAN). Device is still preferred when it HAS the wanted model.
        wanted = model or self.config.inference.default_model
        if wanted:
            for prov, loc in ([(p, "device") for p in self._device]
                              + [(p, "lan") for p in self._lan]):
                if loc == "lan" and policy not in (
                    "local_first_auto_lan", "no_restriction", "local_first_ask_external"
                ):
                    continue
                try:
                    if (await prov.health()).reachable and _has(await prov.list_models(), wanted):
                        return RouteDecision(
                            provider=prov, model=wanted, location=loc,
                            external_data_shared=False,
                            reason=f"Using configured model '{wanted}' on {prov.name} ({loc}).",
                        )
                except Exception:  # noqa: BLE001
                    continue

        # 1 & 2: current device (local Ollama, then local LM Studio).
        for prov in self._device:
            if not (await prov.health()).reachable:
                continue
            models_here = await prov.list_models()
            chosen = model if model and _has(models_here, model) else self._pick_default(models_here)
            if chosen:
                return RouteDecision(
                    provider=prov, model=chosen, location="device", external_data_shared=False,
                    reason=f"Suitable model on this device ({prov.name}).",
                )

        # 3: trusted LAN model (only if allowed by policy).
        if policy in ("local_first_auto_lan", "no_restriction", "local_first_ask_external"):
            for lan in self._lan:
                if not (await lan.health()).reachable:
                    continue
                lan_models = await lan.list_models()
                chosen = model if model and _has(lan_models, model) else self._pick_default(lan_models)
                if chosen:
                    return RouteDecision(
                        provider=lan, model=chosen, location="lan", external_data_shared=False,
                        reason=f"No local model; using trusted LAN provider ({lan.name}).",
                    )

        # 4 & 5: gated remote — ONLY when policy allows external and the user
        # explicitly enabled it. Sends data off-network (labelled).
        if self._remote is not None and policy in ("no_restriction",):
            if (await self._remote.health()).reachable:
                remote_models = await self._remote.list_models()
                chosen = (
                    model
                    or self.config.inference.remote.model
                    or self._pick_default(remote_models)
                )
                if chosen:
                    return RouteDecision(
                        provider=self._remote, model=chosen, location="remote",
                        external_data_shared=True,
                        reason=f"No local/LAN model; using remote provider ({self._remote.name}). "
                               "Data leaves the local network.",
                    )

        # Fall back to a clear disabled response.
        note = "remote inference not enabled"
        if self._remote is not None and policy != "no_restriction":
            note = "a remote provider is configured but policy forbids external inference"
        return RouteDecision(
            provider=DisabledProvider(), model="none", location="unknown",
            external_data_shared=False,
            reason=f"No local or trusted LAN model available; {note}.",
        )


def _has(models: list[ModelInfo], name: str) -> bool:
    return any(m.name == name for m in models)
