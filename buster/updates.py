"""Update checking against the GitHub repo.

Local-first friendly: the only network call is to GitHub's public API to read
the latest release tag — no user data leaves the machine. The result is cached
so we don't hit the network on every launch. Buster never auto-updates; it only
notifies and offers to run the installer when the user agrees.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import httpx

from buster import __version__
from buster.cache import get_cache
from buster.cache.manager import NS_TEMP

_REPO = "buildlyio/buster"
_CACHE_KEY = "update_check"
_CHECK_TTL = 6 * 3600  # re-check at most every 6 hours


def _parse(v: str) -> tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) or (0,)


def is_newer(latest: str, current: str) -> bool:
    return _parse(latest) > _parse(current)


async def latest_release() -> str | None:
    """Return the latest release tag from GitHub, or None if unavailable."""
    url = f"https://api.github.com/repos/{_REPO}/releases/latest"
    try:
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(url, headers={"Accept": "application/vnd.github+json"})
        if r.status_code == 200:
            return r.json().get("tag_name") or None
        # Fall back to tags if there are no formal releases yet.
        async with httpx.AsyncClient(timeout=5.0) as c:
            r = await c.get(f"https://api.github.com/repos/{_REPO}/tags")
        if r.status_code == 200 and r.json():
            return r.json()[0].get("name")
    except Exception:  # noqa: BLE001
        return None
    return None


async def check_for_update(force: bool = False) -> dict:
    """Return {available, current, latest, checked_at}. Cached for _CHECK_TTL."""
    cache = get_cache()
    if not force:
        hit = cache.get(NS_TEMP, _CACHE_KEY)
        if hit and "value" in hit:
            return hit["value"]

    latest = await latest_release()
    result = {
        "current": __version__,
        "latest": latest,
        "available": bool(latest and is_newer(latest, __version__)),
        "checked_at": datetime.now(UTC).astimezone().isoformat(timespec="seconds"),
    }
    cache.put(NS_TEMP, _CACHE_KEY, value=result, ttl=_CHECK_TTL, tags=["update"])
    return result
