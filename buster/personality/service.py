"""Personality service.

Personality is kept separate from facts, memory, skills, permissions, and task
context. It contributes only a compact system-prompt preamble. Changes are
logged, explainable, reversible, resettable, and pausable. Phase 1 does not do
autonomous evolution — only explicit preference updates.
"""

from __future__ import annotations

from datetime import UTC, datetime
from functools import lru_cache

from buster.config import load_config, save_config
from buster.database import get_database

CORE_IDENTITY = (
    "You are Buster, a friendly, capable local assistant. You are practical, "
    "curious, calm under pressure, honest about uncertainty, and respectful of "
    "user control."
)

_PROFILE_STYLES = {
    "friendly_guide": "Warm and encouraging; explain things clearly for a general audience.",
    "quiet_operator": "Terse and operational; minimal chatter, results-first.",
    "technical_partner": "Peer-level technical tone; precise, assumes competence.",
    "research_companion": "Thoughtful and source-aware; careful about evidence and claims.",
    "household_assistant": "Approachable and helpful for everyday home tasks.",
}

_STYLE_RULES = (
    "Be friendly, personable, practical, calm, and clear. Stay lightly curious. "
    "Avoid being overly enthusiastic or verbose. Always be honest about "
    "uncertainty. Never invent facts, sources, devices, or results."
)


def _now() -> str:
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")


class PersonalityService:
    def system_preamble(self) -> str:
        config = load_config()
        profile = config.personality.profile
        style = _PROFILE_STYLES.get(profile, _PROFILE_STYLES["friendly_guide"])
        return f"{CORE_IDENTITY}\n\nStyle profile: {profile} — {style}\n{_STYLE_RULES}"

    def current_profile(self) -> str:
        return load_config().personality.profile

    def set_profile(self, profile: str, reason: str = "user preference") -> None:
        if profile not in _PROFILE_STYLES:
            raise ValueError(f"Unknown profile: {profile}")
        config = load_config()
        old = config.personality.profile
        config.personality.profile = profile  # type: ignore[assignment]
        save_config(config)
        get_database().execute(
            "INSERT INTO personality_changes (field, old_value, new_value, reason, created_at) "
            "VALUES ('profile', ?, ?, ?, ?)",
            (old, profile, reason, _now()),
        )

    def reset(self) -> None:
        self.set_profile("friendly_guide", reason="reset")

    def history(self, limit: int = 50) -> list[dict]:
        rows = get_database().query(
            "SELECT * FROM personality_changes ORDER BY id DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in rows]

    def profiles(self) -> dict[str, str]:
        return dict(_PROFILE_STYLES)


@lru_cache(maxsize=1)
def get_personality() -> PersonalityService:
    return PersonalityService()
