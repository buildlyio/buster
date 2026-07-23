"""Verify that the configured model actually responds.

Onboarding and the launch banner use this to confirm the AI is really connected
— not just that a provider was picked. Sends a tiny prompt and reports a clear
result (working / the actual failure), so "selected but broken" is caught before
the user's first real chat.
"""

from __future__ import annotations

from pydantic import BaseModel

from buster.config import BusterConfig
from buster.models.provider import ChatMessage, ChatRequest
from buster.models.router import ModelRouter


class ModelCheck(BaseModel):
    ok: bool
    model: str = ""
    provider: str = ""
    location: str = ""          # device | lan | remote | unknown
    external_data_shared: bool = False
    detail: str = ""            # human-readable status / error


async def verify_model(config: BusterConfig, timeout: float = 30.0) -> ModelCheck:
    """Route as normal and send a 1-token probe. Returns a ModelCheck."""
    router = ModelRouter(config)
    decision = await router.route()
    if decision.model == "none":
        return ModelCheck(ok=False, detail=decision.reason or "No model available.")

    req = ChatRequest(
        model=decision.model,
        messages=[
            ChatMessage(role="system", content="Reply with exactly: OK"),
            ChatMessage(role="user", content="ping"),
        ],
        max_tokens=5,
        temperature=0.0,
    )
    try:
        resp = await decision.provider.chat(req)
    except Exception as exc:  # noqa: BLE001
        return ModelCheck(
            ok=False, model=decision.model, provider=decision.provider.name,
            location=decision.location, detail=_friendly_error(str(exc)),
        )
    content = (resp.content or "").strip()
    if not content:
        return ModelCheck(
            ok=False, model=decision.model, provider=decision.provider.name,
            location=decision.location, detail="Model returned an empty response.",
        )
    return ModelCheck(
        ok=True, model=decision.model, provider=decision.provider.name,
        location=decision.location, external_data_shared=decision.external_data_shared,
        detail=f"Model responded ({len(content)} chars).",
    )


def _friendly_error(err: str) -> str:
    low = err.lower()
    if "connect" in low or "refused" in low or "timeout" in low or "unreachable" in low:
        return f"Provider unreachable — is it running? ({err[:120]})"
    if "404" in low or "not found" in low:
        return f"Model not found — pull it or pick another. ({err[:120]})"
    if "401" in low or "403" in low or "unauthor" in low:
        return f"Auth failed — check the API key/token. ({err[:120]})"
    return err[:160]
