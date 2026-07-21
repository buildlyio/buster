"""Skill registry.

Skills are Markdown files with YAML-ish frontmatter (compatible in spirit with
open agent-skill conventions). A skill declares instructions, tool requirements,
context requirements, permission expectations, and an optional report template.
A skill can NEVER grant itself new permissions — it only references tools that
already exist with their existing risk levels.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field

from buster.config import get_paths

# Bundled skills ship inside the package; user skills live in the home dir.
_BUNDLED = Path(__file__).parent / "bundled"


class Skill(BaseModel):
    id: str
    name: str
    description: str = ""
    tools: list[str] = Field(default_factory=list)
    context: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    path: str = ""
    instructions: str = ""


def _parse_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    fm_block = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")
    meta: dict = {}
    key = None
    for line in fm_block.splitlines():
        if not line.strip():
            continue
        if line.startswith(("  - ", "- ")) and key:
            meta.setdefault(key, [])
            meta[key].append(line.strip()[2:].strip())
        elif ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip()
            if val:
                meta[key] = val
            else:
                meta[key] = []
    return meta, body


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, Skill] = {}
        self.reload()

    def reload(self) -> None:
        self._skills.clear()
        for base in (_BUNDLED, get_paths().skills_dir):
            if not base.exists():
                continue
            for md in base.glob("*.md"):
                skill = self._load(md)
                if skill:
                    self._skills[skill.id] = skill

    def _load(self, path: Path) -> Skill | None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        meta, body = _parse_frontmatter(text)
        sid = str(meta.get("id") or path.stem)
        return Skill(
            id=sid,
            name=str(meta.get("name") or sid),
            description=str(meta.get("description") or ""),
            tools=meta.get("tools") if isinstance(meta.get("tools"), list) else [],
            context=meta.get("context") if isinstance(meta.get("context"), list) else [],
            permissions=meta.get("permissions") if isinstance(meta.get("permissions"), list) else [],
            path=str(path),
            instructions=body.strip(),
        )

    def all(self) -> list[Skill]:
        return list(self._skills.values())

    def get(self, skill_id: str) -> Skill | None:
        return self._skills.get(skill_id)


@lru_cache(maxsize=1)
def get_skill_registry() -> SkillRegistry:
    return SkillRegistry()
