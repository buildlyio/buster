"""Typed models for Buildly Workspace context (products, features, issues, ...)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class BuildlyProduct(BaseModel):
    id: str
    name: str
    description: str = ""


class BuildlyFeature(BaseModel):
    id: str
    product_id: str
    name: str
    status: str = "proposed"
    description: str = ""


class BuildlyIssue(BaseModel):
    id: str
    product_id: str
    title: str
    status: str = "open"
    feature_id: str = ""


class BuildlyOpportunity(BaseModel):
    id: str
    title: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)


class BuildlyEvent(BaseModel):
    id: str
    title: str
    starts_at: str = ""
    url: str = ""


class BuildlyRelease(BaseModel):
    id: str
    product_id: str
    version: str
    notes: str = ""


class BuildlyNotification(BaseModel):
    id: str
    kind: str
    title: str
    body: str = ""
    created_at: str = ""
