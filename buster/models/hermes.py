"""Hermes model provider — OpenAI-compatible proxy backend.

Phase 2: when `hermes proxy` is running (or `hermes chat -q ... -z` for
oneshot fallbacks), Buster can route prompts through the locally-running
Hermes instance instead of (or in addition to) Ollama/LM Studio.

Every response is labelled ``inference_location="hermes"`` and audited, so
the trail still shows whether data left the device / local network.

Configuration::

    [inference]
    hermes_url = "http://127.0.0.1:8100/v1"   # hermes proxy, or blank
    hermes_model = ""                          # blank = whatever proxy defaults to
"""

from __future__ import annotations

import json
import subprocess
import time
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

# Capability heuristics for models served by Hermes (provider-agnostic — the
# proxy may be backed by OpenAI, Anthropic, local, or anything).
_CODING_HINTS = ("coder", "code", "deepseek", "qwen2.5-coder", "starcoder", "claude")
_VISION_HINTS = ("llava", "vision", "-vl", "bakllava", "moondream", "gpt-4o", "gpt-4v")
_TOOL_HINTS = (
    "llama3", "qwen2.5", "qwen3", "mistral", "firefunction", "command-r",
    "gpt-4", "gpt-4o", "claude", "sonnet", "haiku",
)
_EMBED_HINTS = ("embed", "nomic", "mxbai", "bge", "text-embedding")


class HermèsProvider:
    """An OpenAI-compatible provider backed by a local Hermes proxy.

    Hermes's ``hermes proxy`` subcommand exposes an OpenAI-compat `/v1/*`
    API backed by whatever OAuth provider / model the user is signed into.
    Buster speaks that API, so no Hermes internals are required — this is a
    normal OpenAI-compatible client, same shape as the existing
    ``OpenAICompatibleProvider`` but with Hermes-specific naming, audit
    location, and a fallback to ``hermes chat -q ... -z`` when the proxy
    isn't reachable.
    """

    name = "hermes"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8100/v1",
        location: InferenceLocation = "device",
        timeout: float = 120.0,
        default_model: str = "",
        oneshot_fallback: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.location = location
        self._timeout = timeout
        self.default_model = default_model.strip()
        self.oneshot_fallback = oneshot_fallback
        self._proxied_model = default_model.strip() or None

    # ------------------------------------------------------------------ health

    async def health(self) -> ProviderHealth:
        """Ping the proxy ``/models`` endpoint.

        Falls back to checking whether ``hermes`` is on ``$PATH`` and
        responding to a minimal ``hermes status`` call if the proxy URL is
        unreachable. That makes ``health`` useful even before the user has
        started ``hermes proxy`` — it distinguishes "Hermes installed but
        proxy not running" from "Hermes not installed".
        """
        detail_parts: list[str] = []
        reachable = False
        models_available = 0

        if self.base_url:
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url, timeout=5.0
                ) as c:
                    r = await c.get("/models", timeout=5.0)
                    if r.status_code == 200:
                        data = r.json()
                        models = data.get("data", [])
                        if isinstance(models, list):
                            models_available = len(models)
                        reachable = True
                        detail_parts.append(
                            f"Hermes proxy reachable at {self.base_url}"
                        )
                        if models_available:
                            detail_parts.append(
                                f"({models_available} models available)"
                            )
            except Exception as exc:  # noqa: BLE001
                detail_parts.append(f"proxy unreachable: {exc}")

        # Fallback signal: is ``hermes`` on PATH at all?
        if not reachable:
            hermes_on_path = _which("hermes")
            if hermes_on_path:
                detail_parts.append(
                    f"hermes on PATH ({hermes_on_path}), proxy not reachable"
                )
            else:
                detail_parts.append("hermes not found on PATH")

        return ProviderHealth(
            provider=self.name,
            reachable=reachable,
            location=self.location,
            detail="; ".join(detail_parts) if detail_parts else "unknown",
            models_available=models_available,
        )

    # -------------------------------------------------------------- list models

    async def list_models(self) -> list[ModelInfo]:
        if self.base_url:
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url, timeout=10.0
                ) as c:
                    r = await c.get("/models", timeout=10.0)
                    if r.status_code == 200:
                        data = r.json()
                        models = data.get("data", [])
                        if isinstance(models, list):
                            out: list[ModelInfo] = []
                            for m in models:
                                id_ = m.get("id") or m.get("name", "")
                                # OpenAI-compat "/models" shape: {"id": ..., "owned_by": ...}
                                context = m.get("context_window") or m.get("max_tokens", None)
                                out.append(
                                    ModelInfo(
                                        provider=self.name,
                                        name=id_,
                                        inference_location=self.location,
                                        context_length=int(context)
                                        if isinstance(context, (int, float))
                                        else None,
                                    )
                                )
                            return out
            except Exception:  # noqa: BLE001
                pass

        # Nothing from the proxy — return a synthetic "hermes (oneshot)" entry
        # so the router knows the provider exists and can fall back to the
        # ``hermes chat -q`` path.
        model_name = self.default_model or "hermes (default)"
        return [
            ModelInfo(
                provider=self.name,
                name=model_name,
                inference_location=self.location,
                context_length=8192,
            )
        ]

    # ---------------------------------------------------------- capabilities

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

    # ------------------------------------------------------------------ chat

    async def chat(self, request: ChatRequest) -> ChatResponse:
        # Try the proxy first.
        if self.base_url:
            try:
                resp = await self._proxy_chat(request)
                if resp is not None:
                    return resp
            except Exception:  # noqa: BLE001
                pass

        # Fall back to ``hermes chat -q ... -z`` (oneshot, non-interactive).
        if self.oneshot_fallback:
            return await self._oneshot_chat(request)

        # Nothing available.
        return ChatResponse(
            model=request.model,
            provider=self.name,
            inference_location=self.location,
            content="",
            tool_calls=[],
            external_data_shared=self.location == "remote",
        )

    async def _proxy_chat(self, request: ChatRequest) -> ChatResponse | None:
        """One attempt at the OpenAI-compat proxy. Returns None on failure."""
        payload: dict = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"

        async with httpx.AsyncClient(
            base_url=self.base_url, timeout=self._timeout
        ) as c:
            r = await c.post("/chat/completions", json=payload)
            if r.status_code != 200:
                return None
            data = r.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message", {})
        tool_calls = [
            ToolCall(
                name=tc.get("function", {}).get("name", ""),
                arguments=tc.get("function", {}).get("arguments", {}) or {},
            )
            for tc in (message.get("tool_calls") or [])
        ]
        content = message.get("content") or ""
        if content is None:
            content = ""
        return ChatResponse(
            model=request.model,
            provider=self.name,
            inference_location=self.location,
            content=content,
            tool_calls=tool_calls,
            external_data_shared=self.location == "remote",
        )

    async def _oneshot_chat(self, request: ChatRequest) -> ChatResponse:
        """Fallback: shell out to ``hermes chat -q ... -z``.

        This is deliberately a last resort (no streaming, no tool calls, no
        SSE). It gives Buster a way to use the user's configured Hermes model
        even when ``hermes proxy`` isn't running, at the cost of a process
        spawn per turn.
        """
        hermes_cmd = _which("hermes")
        if not hermes_cmd:
            return ChatResponse(
                model=request.model,
                provider=self.name,
                inference_location=self.location,
                content=(
                    "Hermes is not installed or not on PATH. "
                    "Start ``hermes proxy`` or install Hermes to use this backend."
                ),
                tool_calls=[],
                external_data_shared=False,
            )

        # Build the prompt from the message history (last system + last user).
        system_parts: list[str] = []
        user_parts: list[str] = []
        for m in request.messages:
            if m.role == "system":
                system_parts.append(m.content)
            elif m.role == "user":
                user_parts.append(m.content)
            elif m.role == "assistant":
                # Include the most recent assistant turn so the oneshot has
                # context for multi-turn, but cap total size.
                user_parts.append(f"[assistant]: {m.content}")
        if not user_parts:
            user_parts.append(request.messages[-1].content if request.messages else "")

        preamble = "\n\n".join(system_parts)
        body = "\n\n".join(user_parts)
        prompt = f"{preamble}\n\n{body}" if preamble else body

        # Cap prompt length to something reasonable for a oneshot.
        if len(prompt) > 8000:
            prompt = prompt[:7900] + "\n...[truncated]"

        args = [hermes_cmd, "chat", "-q", prompt, "-z"]
        if request.model and request.model != "hermes (default)":
            args += ["-m", request.model]

        try:
            start = time.monotonic()
            proc = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=min(self._timeout, 120),
            )
            elapsed = time.monotonic() - start
            stdout = proc.stdout.strip()
            if proc.returncode != 0 or not stdout:
                return ChatResponse(
                    model=request.model,
                    provider=self.name,
                    inference_location=self.location,
                    content=(
                        f"(Hermes oneshot failed: {proc.stderr.strip()[:200] or 'non-zero exit'})"
                    ),
                    tool_calls=[],
                    external_data_shared=False,
                )
            # Trim a trailing newline.
            if stdout.endswith("\n"):
                stdout = stdout[:-1]
            return ChatResponse(
                model=request.model,
                provider=self.name,
                inference_location=self.location,
                content=stdout,
                tool_calls=[],
                external_data_shared=False,
            )
        except subprocess.TimeoutExpired:
            return ChatResponse(
                model=request.model,
                provider=self.name,
                inference_location=self.location,
                content="(Hermes oneshot timed out)",
                tool_calls=[],
                external_data_shared=False,
            )
        except Exception as exc:  # noqa: BLE001
            return ChatResponse(
                model=request.model,
                provider=self.name,
                inference_location=self.location,
                content=f"(Hermes oneshot error: {exc})",
                tool_calls=[],
                external_data_shared=False,
            )

    # --------------------------------------------------------------- embed

    async def embed(self, texts: list[str]) -> list[list[float]]:
        # Use the proxy's embeddings endpoint if available; otherwise return
        # dummy embeddings so callers that optionalize on embed don't crash.
        if not self.base_url:
            return [[0.0] * 1536 for _ in texts]
        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self._timeout
            ) as c:
                out: list[list[float]] = []
                for text in texts:
                    r = await c.post(
                        "/embeddings",
                        json={"model": "text-embedding-3-small", "input": text},
                    )
                    if r.status_code == 200:
                        data = r.json()
                        emb = (
                            data.get("data", [{}])[0]
                            .get("embedding", [])
                        )
                        out.append(emb if isinstance(emb, list) else [0.0] * 1536)
                    else:
                        out.append([0.0] * 1536)
                return out
        except Exception:  # noqa: BLE001
            return [[0.0] * 1536 for _ in texts]

    # --------------------------------------------------------- streaming (optional)

    async def chat_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """Yield content deltas from the proxy's streaming endpoint.

        Never yields reasoning tokens — only final content deltas, to match
        the rest of Buster's provider contract.
        """
        if not self.base_url:
            return
        payload: dict = {
            "model": request.model,
            "messages": [m.model_dump() for m in request.messages],
            "temperature": request.temperature,
            "stream": True,
        }
        if request.max_tokens:
            payload["max_tokens"] = request.max_tokens
        if request.tools:
            payload["tools"] = request.tools
            payload["tool_choice"] = "auto"

        try:
            async with httpx.AsyncClient(
                base_url=self.base_url, timeout=self._timeout
            ) as c:
                async with c.stream("POST", "/chat/completions", json=payload) as r:
                    r.raise_for_status()
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        if line.startswith("data:"):
                            payload_text = line[5:].strip()
                            if payload_text == "[DONE]":
                                break
                            try:
                                chunk = json.loads(payload_text)
                            except json.JSONDecodeError:
                                continue
                            delta = (
                                chunk.get("choices", [{}])[0]
                                .get("delta", {})
                                .get("content", "")
                            )
                            if delta:
                                yield delta
        except Exception:  # noqa: BLE001
            return


def _which(name: str) -> str | None:
    """Return the absolute path to ``name`` on PATH, or None."""
    import shutil

    return shutil.which(name)
