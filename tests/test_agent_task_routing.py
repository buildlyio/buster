"""Task classification + tool-pack routing in the agent loop.

Guards two invariants that were previously broken:
  1. Coding/dev prompts route to the ``coding`` kind and can actually reach the
     read-only terminal/coding tools (the packs were registered but unreachable).
  2. The risk-2 members of those packs are NEVER auto-selected — they stay gated
     behind explicit confirmation regardless of task kind.
"""

from buster.agent.loop import _classify, _tools_for_task
from buster.permissions import RiskLevel
from buster.tools import get_registry

# The write-ish tools that must never appear in an auto-run selection.
GATED_TOOLS = {"terminal.run", "terminal.patch_file", "coding.run", "coding.patch"}


def test_coding_prompts_classify_as_coding():
    for prompt in (
        "fix the bug in this repo",
        "run the tests",
        "what is the git diff",
        "grep for the handler function",
        "refactor this file",
    ):
        assert _classify(prompt) == "coding", prompt


def test_non_coding_prompts_are_unaffected():
    assert _classify("hello there") == "chat"
    assert _classify("compare two sources") == "research"
    assert _classify("check cpu and memory") == "diagnostic"


def test_coding_kind_exposes_readonly_pack_tools():
    reg = get_registry()
    ids = {t.id for t in _tools_for_task("coding", "macos", reg)}
    # Read-only tools from both new packs are now reachable.
    for expected in (
        "terminal.sniff",
        "terminal.read_file",
        "terminal.grep",
        "coding.repo_info",
        "coding.git_diff",
        "coding.read",
    ):
        assert expected in ids, expected


def test_gated_tools_never_auto_selected_in_any_kind():
    reg = get_registry()
    for kind in ("chat", "coding", "research", "diagnostic"):
        ids = {t.id for t in _tools_for_task(kind, "macos", reg)}
        assert not (GATED_TOOLS & ids), f"gated tool leaked into kind={kind}"


def test_all_auto_selected_tools_are_within_safe_risk():
    reg = get_registry()
    for kind in ("chat", "coding", "research", "diagnostic"):
        for t in _tools_for_task(kind, "macos", reg):
            assert t.risk_level <= RiskLevel.SAFE_BUSTER, (kind, t.id)
