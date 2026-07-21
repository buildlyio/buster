"""Web fetch + readable-text extraction.

Fetched content is cached and treated as UNTRUSTED data — it never becomes
instructions to the model. We do not attempt to bypass access controls.
"""

from __future__ import annotations

import hashlib
import re

import httpx
from pydantic import BaseModel
from selectolax.parser import HTMLParser

from buster.cache import get_cache
from buster.cache.manager import NS_WEB

_UA = "Buster/0.1 (+https://buster.buildly.io; local-first assistant)"


class FetchedPage(BaseModel):
    url: str
    status: int
    title: str = ""
    published_at: str = ""
    text: str = ""
    content_hash: str = ""
    from_cache: bool = False
    untrusted: bool = True


def _extract_title(tree: HTMLParser) -> str:
    node = tree.css_first("meta[property='og:title']")
    if node and node.attributes.get("content"):
        return node.attributes["content"].strip()
    if tree.css_first("title"):
        return tree.css_first("title").text(strip=True)
    h1 = tree.css_first("h1")
    return h1.text(strip=True) if h1 else ""


def _extract_date(tree: HTMLParser) -> str:
    for sel, attr in [
        ("meta[property='article:published_time']", "content"),
        ("meta[name='date']", "content"),
        ("meta[name='publish-date']", "content"),
        ("time[datetime]", "datetime"),
    ]:
        node = tree.css_first(sel)
        if node and node.attributes.get(attr):
            return node.attributes[attr].strip()
    return ""


def _extract_text(tree: HTMLParser) -> str:
    for tag in ("script", "style", "nav", "footer", "header", "aside", "noscript"):
        for node in tree.css(tag):
            node.decompose()
    main = tree.css_first("article") or tree.css_first("main") or tree.body
    # Separator=" " keeps inline elements from being glued together
    # ("RaspberryPi5"); we then normalize runs of whitespace and rebuild
    # paragraph breaks from block-level newlines in the source.
    text = main.text(separator=" ") if main else tree.text(separator=" ")
    # Collapse horizontal whitespace, keep intentional line breaks.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


async def fetch_url(url: str, use_cache: bool = True) -> FetchedPage:
    cache = get_cache()
    ckey = hashlib.sha256(url.encode()).hexdigest()
    if use_cache:
        hit = cache.get(NS_WEB, ckey)
        if hit and "value" in hit:
            page = FetchedPage.model_validate(hit["value"])
            page.from_cache = True
            return page

    async with httpx.AsyncClient(
        headers={"User-Agent": _UA}, follow_redirects=True, timeout=20.0
    ) as client:
        resp = await client.get(url)
        html = resp.text

    tree = HTMLParser(html)
    text = _extract_text(tree)
    page = FetchedPage(
        url=str(resp.url),
        status=resp.status_code,
        title=_extract_title(tree),
        published_at=_extract_date(tree),
        text=text,
        content_hash=hashlib.sha256(text.encode()).hexdigest(),
    )
    cache.put(NS_WEB, ckey, value=page.model_dump(), ttl=86400, tags=["web"])
    return page
