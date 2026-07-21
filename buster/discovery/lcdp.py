"""LCDP manifest model (schema lcdp/v1) and Buster's own manifest.

Discovery is read-only. Buster never connects automatically. See docs/LCDP.md
for the specification draft.
"""

from __future__ import annotations

import socket

from pydantic import BaseModel, Field

from buster import __version__
from buster.config import load_config


class LCDPManifest(BaseModel):
    schema_: str = Field(default="lcdp/v1", alias="schema")
    id: str
    name: str
    product: str = ""
    version: str = ""
    host: str = ""
    api_url: str = ""
    health_url: str = ""
    mcp_url: str = ""
    capabilities: list[str] = Field(default_factory=list)
    authentication: str = "none"
    permissions: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class BusterNodeManifest(LCDPManifest):
    """Buster-specific manifest advertised for node discovery."""

    device_type: str = ""
    platform: str = ""
    models: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    toolpacks: list[str] = Field(default_factory=list)
    allowed_workloads: list[str] = Field(default_factory=list)
    trust_requirements: str = "manual"


def build_self_manifest() -> BusterNodeManifest:
    config = load_config()
    host = socket.gethostname()
    base = config.base_url
    return BusterNodeManifest(
        id=f"buster.{host}",
        name=f"Buster on {host}",
        product="buster",
        version=__version__,
        host=host,
        api_url=f"{base}/api",
        health_url=f"{base}/api/health",
        mcp_url="",
        capabilities=[
            "research.web",
            "diagnostics.system",
            "diagnostics.network",
            "reports.markdown",
        ],
        authentication="local-token" if config.server.lan_access else "none",
        permissions=["read"],
        device_type="workstation",
        platform="",
        allowed_workloads=["capability_query"],
        trust_requirements="manual",
    )
