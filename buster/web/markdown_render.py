"""Server-side Markdown → safe HTML for the web UI.

Uses markdown-it-py (already a dependency via Rich). Rendered with html=False so
any inline/raw HTML in the (possibly untrusted) source is ESCAPED, not executed —
meaning markdown-it only ever emits its own known-safe tag set. The only residual
XSS vector is a dangerous URL scheme in a generated link, which we neutralize with
a regex pass. Self-contained: no external CDN, no network.
"""

from __future__ import annotations

import re
from functools import lru_cache

# Neutralize javascript:/data:/vbscript: in hrefs that markdown-it emitted.
_BAD_HREF = re.compile(
    r'href="\s*(?:javascript|data|vbscript):[^"]*"', re.IGNORECASE
)


@lru_cache(maxsize=1)
def _md():
    from markdown_it import MarkdownIt

    # html=False → raw HTML in source is escaped (no passthrough), so the output
    # contains only markdown-it's own safe tags. linkify autolinks bare URLs.
    return MarkdownIt("commonmark", {"html": False, "linkify": True}).enable("table")


def render_markdown(md_text: str) -> str:
    """Return safe HTML for a Markdown string. Safe for untrusted content."""
    if not md_text:
        return ""
    try:
        html = _md().render(md_text)
        # Neutralize dangerous link schemes.
        html = _BAD_HREF.sub('href="#"', html)
        return html
    except Exception:  # noqa: BLE001
        import html as _html

        return f"<pre>{_html.escape(md_text)}</pre>"
