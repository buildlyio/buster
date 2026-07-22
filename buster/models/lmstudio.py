"""LM Studio provider (OpenAI-compatible local server).

LM Studio exposes an OpenAI-compatible API (default http://localhost:1234/v1).
This adapter also serves any other OpenAI-compatible endpoint the user points at
(self-hosted TGI, vLLM, etc.) via the same shape — see providers that set a
different base_url/location.
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


class OpenAICompatibleProvider:
    """Generic OpenAI-compatible chat provider (LM Studio, TGI, vLLM, ...)."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:1234/v1",
        location: InferenceLocation = "device",
        api_key: str = "",
        name: str = "lmstudio",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.location = location
        self.name = name
        self._api_key = api_key
        self._timeout = timeout

    def _headers(self) -> dict:
        h = {"Content-Type": "application/json"}
        if self._api_key:
            h["Authorization"] = f"Bearer {self._api_key}"
        return h

    async def health(self) -> ProviderHealth:
        try:
            async with httpx.AsyncClient(timeout=5.0) as c:
                r = await c.get(f"{self.base_url}/models", headers=self._headers())
                r.raise_for_status()
                models = r.json().get("data", [])
            return ProviderHealth(
                provider=self.name, reachable=True, location=self.location,
                detail=f"{self.name} reachable at {self.base_url}", models_available=len(models),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                provider=self.name, reachable=False, location=self.location,
                detail=f"Unreachable: {exc}",
            )

    async def list_models(self) -> list[ModelInfo]:
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.get(f"{self.base_url}/models", headers=self._headers())
            r.raise_for_status()
            data = r.json()
        return [
            ModelInfo(provider=self.name, name=m.get("id", ""), inference_location=self.location)
            for m in data.get("data", [])
        ]

    async def capabilities(self, model: str) -> ModelCapabilities:
        # OpenAI-compatible servers vary; assume general chat, tool-calling
        # optional. Kept conservative.
        return ModelCapabilities(context_length=8192, speed_class="medium", quality_class="good")

    async def chat(self, request: ChatRequest) -> ChatResponse:
        payload = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "stream": False,
        }
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            r = await c.post(f"{self.base_url}/chat/completions", json=payload, headers=self._headers())
            r.raise_for_status()
            data = r.json()
        content = ""
        if data.get("choices"):
            content = data["choices"][0].get("message", {}).get("content", "")
        return ChatResponse(
            model=request.model, provider=self.name, inference_location=self.location,
            content=content, external_data_shared=self.location == "remote",
        )

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with httpx.AsyncClient(timeout=self._timeout) as c:
            for t in texts:
                r = await c.post(f"{self.base_url}/embeddings",
                                 json={"input": t, "model": "text-embedding"},
                                 headers=self._headers())
                if r.status_code == 200 and r.json().get("data"):
                    out.append(r.json()["data"][0].get("embedding", []))
                else:
                    out.append([])
        return out
