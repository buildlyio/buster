"""Suggest-and-confirm association between a local repo and a Labs product.

Buster proposes a match; nothing is written to Labs or .buildly/project.yaml
without explicit confirmation (spec: "never silently convert inferred info into
approved product truth"). Matching is a simple, transparent name/slug heuristic —
the user always sees why a suggestion was made.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

from pydantic import BaseModel


class ProductMatch(BaseModel):
    product_id: str
    product_name: str
    score: float
    reason: str


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def suggest_matches(repo_path: str, products: list[dict], limit: int = 5) -> list[ProductMatch]:
    """Rank Labs products against the repo's folder name. Transparent scoring."""
    repo_name = Path(repo_path).expanduser().resolve().name
    repo_slug = _slug(repo_name)
    matches: list[ProductMatch] = []
    for p in products:
        pid = str(p.get("id") or p.get("uuid") or p.get("product_uuid") or "")
        pname = str(p.get("name") or p.get("product_name") or "")
        if not pid or not pname:
            continue
        pslug = _slug(pname)
        if pslug == repo_slug:
            score, reason = 1.0, "exact name match"
        elif repo_slug in pslug or pslug in repo_slug:
            score, reason = 0.8, "name contains the other"
        else:
            score = SequenceMatcher(None, repo_slug, pslug).ratio()
            reason = f"name similarity {score:.0%}"
        matches.append(ProductMatch(product_id=pid, product_name=pname,
                                    score=round(score, 3), reason=reason))
    matches.sort(key=lambda m: m.score, reverse=True)
    return matches[:limit]


def write_binding(repo_path: str, product_id: str, product_name: str,
                  labs_url: str = "") -> Path:
    """Write .buildly/project.yaml. Only called after explicit confirmation."""
    import yaml

    proj_dir = Path(repo_path).expanduser() / ".buildly"
    proj_dir.mkdir(parents=True, exist_ok=True)
    path = proj_dir / "project.yaml"
    path.write_text(yaml.safe_dump({
        "schema": "provisional/0",
        "product_id": product_id,
        "product_name": product_name,
        "labs_url": labs_url,
    }))
    return path
