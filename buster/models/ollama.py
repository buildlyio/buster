"""Ollama model provider — the primary local-first backend for Phase 1.

Supports the local daemon and manually configured LAN endpoints. Uses the
native Ollama HTTP API (``/api/tags``, ``/api/chat``, ``/api/embeddings``).
"""

from __future__ import annotations

from collections.abc import AsyncIterator

import httpx

from buster.models.provider import (
    ChatRequest,
    ChatResponse,
    InferenceLocation,
    ModelCapabilities,
    ModelInfo,
    ProviderHealth,
    ToolCall,
)

# Heuristic capability hints keyed on model-name substrings.
_CODING_HINTS = ("coder", "code", "deepseek", "qwen2.5-coder", "starcoder")
_VISION_HINTS = ("llava", "vision", "-vl", "bakllava", "moondream")
# Models known to accept Ollama's tool-calling API. Gemma3/Gemma4 do NOT.
_TOOL_HINTS = ("llama3", "qwen2.5", "qwen3", "mistral", "firefunction", "command-r")
_EMBED_HINTS = ("embed", "nomic", "mxbai", "bge")


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        location: InferenceLocation = "device",
        timeout: float = 120.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.location = location
        self._timeout = timeout

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(base_url=self.base_url, timeout=self._timeout)

    async def health(self) -> ProviderHealth:
        try:
            async with self._client() as c:
                r = await c.get("/api/tags", timeout=5.0)
                r.raise_for_status()
                models = r.json().get("models", [])
            return ProviderHealth(
                provider=self.name,
                reachable=True,
                location=self.location,
                detail=f"Ollama reachable at {self.base_url}",
                models_available=len(models),
            )
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(
                provider=self.name,
                reachable=False,
                location=self.location,
                detail=f"Unreachable: {exc}",
            )

    async def list_models(self) -> list[ModelInfo]:
        async with self._client() as c:
            r = await c.get("/api/tags")
            r.raise_for_status()
            data = r.json()
        out: list[ModelInfo] = []
        for m in data.get("models", []):
            details = m.get("details", {})
            out.append(
                ModelInfo(
                    provider=self.name,
                    name=m.get("name", ""),
                    inference_location=self.location,
                    size_bytes=m.get("size"),
                    context_length=_context_from_details(details),
                )
            )
        return out

    async def capabilities(self, model: str) -> ModelCapabilities:
        m = model.lower()
        return ModelCapabilities(
            tool_calling=any(h in m for h in _TOOL_HINTS),
            structured_output=any(h in m for h in _TOOL_HINTS),
            vision=any(h in m for h in _VISION_HINTS),
            embedding=any(h in m for h in _EMBED_HINTS),
            coding=any(h in m for h in _CODING_HINTS),
            context_length=8192,
            speed_class="medium",
            quality_class="good",
        )

    async def chat(self, request: ChatRequest) -> ChatResponse:
        payload = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": False,
            "options": {"temperature": request.temperature},
        }
        if request.tools:
            payload["tools"] = request.tools
        async with self._client() as c:
            r = await c.post("/api/chat", json=payload)
            # Some models (e.g. gemma3/gemma4) reject the tools field with a 400.
            # Fall back to a plain chat so the assistant still responds.
            if r.status_code == 400 and "tools" in payload:
                payload.pop("tools", None)
                r = await c.post("/api/chat", json=payload)
            r.raise_for_status()
            data = r.json()
        msg = data.get("message", {})
        tool_calls = [
            ToolCall(
                name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments", {}) or {},
            )
            for tc in msg.get("tool_calls", []) or []
        ]
        return ChatResponse(
            model=request.model,
            provider=self.name,
            inference_location=self.location,
            content=msg.get("content", ""),
            tool_calls=tool_calls,
            external_data_shared=self.location == "remote",
        )

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """Yield content deltas. Never yields reasoning tokens."""
        import json

        payload = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "stream": True,
            "options": {"temperature": request.temperature},
        }
        async with self._client() as c:
            async with c.stream("POST", "/api/chat", json=payload) as r:
                r.raise_for_status()
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    chunk = json.loads(line)
                    delta = chunk.get("message", {}).get("content", "")
                    if delta:
                        yield delta
                    if chunk.get("done"):
                        break

    async def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        async with self._client() as c:
            for text in texts:
                r = await c.post(
                    "/api/embeddings",
                    json={"model": "nomic-embed-text", "prompt": text},
                )
                r.raise_for_status()
                out.append(r.json().get("embedding", []))
        return out


def _context_from_details(details: dict) -> int | None:
    # Ollama /api/tags doesn't reliably expose context length; leave None.
    return None
