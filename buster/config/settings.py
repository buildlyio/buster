"""TOML-backed configuration with validated defaults.

The config file mirrors the sections documented in the product spec. All
sections have safe defaults, so Buster runs with no config file present.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover
    import tomli as tomllib

import tomli_w

from buster.config.paths import get_paths

InferencePolicy = Literal[
    "local_only",
    "local_first_ask_external",
    "local_first_auto_lan",
    "no_restriction",
]


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8765
    lan_access: bool = False
    # Token required when lan_access is enabled. Generated at first LAN enable.
    lan_token: str = ""

    # --- LAN naming --------------------------------------------------------
    # Multiple Busters can share a LAN, so each node gets a UNIQUE name:
    #   <node_name>.<domain>   e.g. "alderaan.buster.home"
    # plus a convenience bare alias "<domain>" (buster.local / buster.home)
    # for the single-node case.
    #
    # `domain`: the suffix. mDNS can auto-publish ".local"; other suffixes
    # (e.g. "buster.home" via Pi-hole / local DNS) must be added to that DNS
    # server — `buster doctor` prints the exact records. See docs/INSTALL.md.
    domain: str = "buster.local"
    # `node_name`: this node's label. Blank = derive from the machine hostname.
    node_name: str = ""
    # Also advertise the bare `domain` as a "whichever answers" alias.
    advertise_alias: bool = True


class RemoteProviderConfig(BaseModel):
    """A user-configured remote / OpenAI-compatible endpoint (opt-in).

    Using this sends prompts OFF the local network — Buster labels every such
    response and only routes here when policy allows external inference.
    """

    enabled: bool = False
    name: str = "remote"
    base_url: str = ""          # e.g. https://api-inference.huggingface.co/... or a self-hosted URL
    api_key: str = ""           # kept out of logs/prompts/reports (redacted)
    model: str = ""


class InferenceConfig(BaseModel):
    policy: InferencePolicy = "local_first_ask_external"
    default_provider: str = "ollama"       # ollama | lmstudio | remote
    default_model: str = ""
    ollama_url: str = "http://127.0.0.1:11434"
    # Manually configured trusted LAN Ollama endpoints.
    lan_ollama_urls: list[str] = Field(default_factory=list)
    # LM Studio / OpenAI-compatible endpoints (device or LAN), base URLs incl. /v1.
    lmstudio_urls: list[str] = Field(default_factory=list)
    # Gated remote provider (off by default; sends data off-network when used).
    remote: RemoteProviderConfig = Field(default_factory=RemoteProviderConfig)
    # Max agent loop steps.
    max_steps: int = 8
    tool_timeout_seconds: int = 30


class CacheConfig(BaseModel):
    memory_limit_mb: int = 64
    disk_limit_mb: int = 1024
    default_ttl_seconds: int = 3600


class DiscoveryConfig(BaseModel):
    enabled: bool = True
    advertise_buster: bool = True
    scan_local_network: bool = False
    # Manually configured service manifest URLs.
    service_urls: list[str] = Field(default_factory=list)


class BuildlyConfig(BaseModel):
    workspace_enabled: bool = False
    mode: Literal["none", "local_mcp", "hosted_mcp", "account"] = "none"
    # Hosted bb-agent-manager MCP endpoint (SSE), e.g. http://bespin.home:8000/sse.
    # When set, Buster prefers this; otherwise it launches the local buildly-mcp
    # over stdio. Discovery can also fill this in from an LCDP/mDNS match.
    mcp_url: str = ""
    # Command to launch the local bb-agent-manager over stdio (fallback).
    mcp_local_command: str = "buildly-mcp"
    account_email: str = ""


class PersonalityConfig(BaseModel):
    profile: Literal[
        "friendly_guide",
        "quiet_operator",
        "technical_partner",
        "research_companion",
        "household_assistant",
        "developer",
    ] = "friendly_guide"
    learning_enabled: bool = False


class RuntimesConfig(BaseModel):
    """Coexistence with other agent runtimes (Hermes, OpenClaw, ...)."""

    detect: bool = True
    # Submitting executable tasks to real external runtimes is off by default.
    allow_task_submission: bool = False


class SchedulerConfig(BaseModel):
    enabled: bool = True
    poll_interval_seconds: int = 60
    # Deterministic alert thresholds.
    low_disk_percent: float = 90.0
    high_memory_percent: float = 90.0


class OnboardingConfig(BaseModel):
    completed: bool = False


class BusterConfig(BaseModel):
    server: ServerConfig = Field(default_factory=ServerConfig)
    inference: InferenceConfig = Field(default_factory=InferenceConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    discovery: DiscoveryConfig = Field(default_factory=DiscoveryConfig)
    buildly: BuildlyConfig = Field(default_factory=BuildlyConfig)
    personality: PersonalityConfig = Field(default_factory=PersonalityConfig)
    runtimes: RuntimesConfig = Field(default_factory=RuntimesConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)
    onboarding: OnboardingConfig = Field(default_factory=OnboardingConfig)

    @property
    def base_url(self) -> str:
        host = self.server.host if self.server.host != "0.0.0.0" else "127.0.0.1"
        return f"http://{host}:{self.server.port}"


def load_config(path: Path | None = None) -> BusterConfig:
    """Load config from TOML, falling back to validated defaults."""
    path = path or get_paths().config_file
    if not path.exists():
        return BusterConfig()
    with path.open("rb") as fh:
        raw = tomllib.load(fh)
    return BusterConfig.model_validate(raw)


def save_config(config: BusterConfig, path: Path | None = None) -> Path:
    """Persist config to TOML. Returns the written path."""
    path = path or get_paths().config_file
    path.parent.mkdir(parents=True, exist_ok=True)
    data = config.model_dump(mode="json")
    with path.open("wb") as fh:
        tomli_w.dump(data, fh)
    return path
