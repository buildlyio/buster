"""Model-provider protocol — independent of any specific backend.

Phase 1 ships OllamaProvider and DisabledProvider, plus a config interface for
future OpenAI-compatible providers. Everything records inference location so the
audit trail can show whether data left the device or the local network.
"""

from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, Field

InferenceLocation = Literal["device", "lan", "remote", "unknown"]
SpeedClass = Literal["fast", "medium", "slow", "unknown"]
QualityClass = Literal["basic", "good", "strong", "unknown"]


class ModelInfo(BaseModel):
    provider: str
    name: str
    inference_location: InferenceLocation = "device"
    estimated_ram_gb: float | None = None
    context_length: int | None = None
    size_bytes: int | None = None


class ModelCapabilities(BaseModel):
    tool_calling: bool = False
    structured_output: bool = False
    vision: bool = False
    embedding: bool = False
    coding: bool = False
    context_length: int = 4096
    speed_class: SpeedClass = "unknown"
    quality_class: QualityClass = "unknown"


class ProviderHealth(BaseModel):
    provider: str
    reachable: bool
    location: InferenceLocation
    detail: str = ""
    models_available: int = 0


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str


class ChatRequest(BaseModel):
    model: str
    messages: list[ChatMessage]
    stream: bool = False
    temperature: float = 0.7
    max_tokens: int | None = None
    tools: list[dict] | None = None


class ToolCall(BaseModel):
    name: str
    arguments: dict = Field(default_factory=dict)


class ChatResponse(BaseModel):
    model: str
    provider: str
    inference_location: InferenceLocation
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    external_data_shared: bool = False


@runtime_checkable
class ModelProvider(Protocol):
    name: str

    async def health(self) -> ProviderHealth: ...

    async def list_models(self) -> list[ModelInfo]: ...

    async def capabilities(self, model: str) -> ModelCapabilities: ...

    async def chat(self, request: ChatRequest) -> ChatResponse: ...

    async def embed(self, texts: list[str]) -> list[list[float]]: ...
