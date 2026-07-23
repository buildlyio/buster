"""Anthropic (Claude) provider — hosted, gated-remote only.

Implements the ModelProvider shape over the Claude Messages API. Used ONLY when
the user opts into a remote provider AND policy allows external inference; every
response is labelled external_data_shared=True and audited upstream.

Defaults to a current Claude model; the exact model is set in config.
"""

from __future__ import annotations

import httpx

from buster.models.provider import (
    ChatRequest,
    ChatResponse,
    InferenceLocation,
    ModelCapabilities,
    ModelInfo,
    ProviderHealth,
)

_DEFAULT_BASE = "https://api.anthropic.com"
_API_VERSION = "2023-06-01"
# Sensible current default; overridable via config.inference.remote.model.
_DEFAULT_MODEL = "claude-sonnet-4-5"


class AnthropicProvider:
    name = "anthropic"

    def __init__(
        self,
        api_key: str,
        base_url: str = "",
        location: InferenceLocation = "remote",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = (base_url or _DEFAULT_BASE).rstrip("/")
        self.location = location
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _API_VERSION,
            "content-type": "application/json",
        }

    async def health(self) -> ProviderHealth:
        if not self._api_key:
            return ProviderHealth(provider=self.name, reachable=False, location=self.location,
                                  detail="No Anthropic API key configured.")
        # A cheap reachability probe (a tiny message would cost tokens; just
        # confirm the endpoint is up and the key is well-formed enough to try).
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(self.base_url, timeout=5.0)
            return ProviderHealth(provider=self.name, reachable=r.status_code < 500,
                                  location=self.location, detail="Anthropic API reachable")
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(provider=self.name, reachable=False,
                                  location=self.location, detail=f"Unreachable: {exc}")

    async def list_models(self) -> list[ModelInfo]:
        # Anthropic has no open list endpoint; report the configured default.
        return [ModelInfo(provider=self.name, name=_DEFAULT_MODEL,
                          inference_location=self.location)]

    async def capabilities(self, model: str) -> ModelCapabilities:
        return ModelCapabilities(tool_calling=True, structured_output=True, vision=True,
                                 coding=True, context_length=200000,
                                 speed_class="medium", quality_class="strong")

    async def chat(self, request: ChatRequest) -> ChatResponse:
        # Claude keeps the system prompt out of messages.
        system = "\n".join(m.content for m in request.messages if m.role == "system")
        msgs = [{"role": m.role, "content": m.content}
                for m in request.messages if m.role in ("user", "assistant")]
        payload = {
            "model": request.model or _DEFAULT_MODEL,
            "max_tokens": request.max_tokens or 1024,
            "messages": msgs,
        }
        if system:
            payload["system"] = system
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.post(f"{self.base_url}/v1/messages", json=payload, headers=self._headers())
            r.raise_for_status()
            data = r.json()
        content = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                content += block.get("text", "")
        return ChatResponse(
            model=payload["model"], provider=self.name, inference_location=self.location,
            content=content, external_data_shared=True,
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Anthropic doesn't provide embeddings; return empties (use a local
        # embedding model instead).
        return [[] for _ in texts]
