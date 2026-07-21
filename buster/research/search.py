"""Configurable web-search provider interface.

Phase 1 ships a lightweight DuckDuckGo HTML provider (no API key). The interface
lets other providers (SearXNG, Brave, etc.) be added later. Results are data.
"""

from __future__ import annotations

from typing import Protocol
import httpx
from pydantic import BaseModel
from selectolax.parser import HTMLParser

_UA = "Buster/0.1 (+https://buster.buildly.io)"


class SearchResultItem(BaseModel):
    title: str
    url: str
    snippet: str = ""


class SearchProvider(Protocol):
    name: str

    async def search(self, query: str, limit: int = 8) -> list[SearchResultItem]: ...


class DuckDuckGoProvider:
    name = "duckduckgo"

    async def search(self, query: str, limit: int = 8) -> list[SearchResultItem]:
        async with httpx.AsyncClient(
            headers={"User-Agent": _UA}, timeout=15.0, follow_redirects=True
        ) as c:
            r = await c.post("https://html.duckduckgo.com/html/", data={"q": query})
        tree = HTMLParser(r.text)
        items: list[SearchResultItem] = []
        for res in tree.css(".result"):
            link = res.css_first("a.result__a")
            if not link:
                continue
            href = link.attributes.get("href", "")
            snippet_node = res.css_first(".result__snippet")
            items.append(
                SearchResultItem(
                    title=link.text(strip=True),
                    url=_clean_ddg(href),
                    snippet=snippet_node.text(strip=True) if snippet_node else "",
                )
            )
            if len(items) >= limit:
                break
        return items


def _clean_ddg(href: str) -> str:
    # DDG HTML wraps links in a redirect: //duckduckgo.com/l/?uddg=<encoded>
    from urllib.parse import parse_qs, unquote, urlparse

    if "uddg=" in href:
        qs = parse_qs(urlparse("https:" + href if href.startswith("//") else href).query)
        if "uddg" in qs:
            return unquote(qs["uddg"][0])
    return href


def get_search_provider(name: str = "duckduckgo") -> SearchProvider:
    return DuckDuckGoProvider()
