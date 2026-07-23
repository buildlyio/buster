"""Research → proposed solutions + one-click agent action, and MD→HTML render."""

import pytest

from buster.research import solutions
from buster.web.markdown_render import render_markdown


# -- markdown rendering -------------------------------------------------------

def test_markdown_renders_html():
    html = render_markdown("# Title\n\n**bold** and a list:\n\n- one\n- two")
    assert "<h1>Title</h1>" in html
    assert "<strong>bold</strong>" in html
    assert "<li>one</li>" in html


def test_markdown_escapes_script():
    html = render_markdown("hi <script>alert(1)</script>")
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_markdown_neutralizes_js_links():
    # A normal markdown link renders as a live href.
    html = render_markdown("[click](https://ok.com)")
    assert 'href="https://ok.com"' in html
    # Raw HTML anchors are escaped (html=False), so no live <a> is produced.
    bad = render_markdown('<a href="javascript:alert(1)">x</a>')
    assert "<a " not in bad  # escaped to &lt;a … — never a live link
    # A markdown link with a javascript: scheme is neutralized to href="#".
    md_js = render_markdown("[x](javascript:alert(1))")
    assert 'href="javascript:' not in md_js


def test_markdown_tables():
    html = render_markdown("| A | B |\n|---|---|\n| 1 | 2 |")
    assert "<table>" in html and "<td>1</td>" in html


# -- solution parsing ---------------------------------------------------------

def test_parse_solutions_title_detail():
    text = ("TITLE: First\nDETAIL: do the thing\n---\n"
            "**TITLE:** Second\n**DETAIL:** another thing")
    sols = solutions._parse_solutions(text)
    assert [s.title for s in sols] == ["First", "Second"]
    assert sols[0].detail == "do the thing"


def test_parse_solutions_numbered_fallback():
    text = "1. Use a Pi-hole record — for .home names\n2. Advertise mDNS — for .local"
    sols = solutions._parse_solutions(text)
    assert len(sols) == 2
    assert sols[0].title.startswith("Use a Pi-hole")


def test_deterministic_solutions_never_empty():
    from buster.reports.model import Finding

    sols = solutions._deterministic_solutions("q", [Finding(statement="x")])
    assert sols  # always proposes at least one direction


@pytest.mark.asyncio
async def test_synthesize_falls_back_without_model(monkeypatch):
    from buster.reports.model import Finding

    async def no_model(*a, **k):
        return []

    monkeypatch.setattr(solutions, "_model_solutions", no_model)

    async def fake_action(q, s):
        return solutions.RecommendedAction(summary="x", prompt="p")

    monkeypatch.setattr(solutions, "build_recommended_action", fake_action)
    ss = await solutions.synthesize("how to X", [Finding(statement="clue")])
    assert ss.engine == "deterministic"
    assert ss.solutions
    assert ss.action is not None
    # one-click design: when-options include now/schedule/queue
    assert "now" in ss.action.when_options


@pytest.mark.asyncio
async def test_recommended_action_has_where_and_when(monkeypatch):
    action = await solutions.build_recommended_action("q", [
        solutions.ProposedSolution(title="Do it", detail="d")])
    assert action.prompt
    assert "now" in action.when_options
    # runtime_options may be empty in a bare env, but the field exists.
    assert isinstance(action.runtime_options, list)
