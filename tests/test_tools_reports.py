import pytest

from buster.reports import get_report_store
from buster.reports.model import Finding, Report, ReportSource
from buster.reports.store import slugify
from buster.tools import get_registry
from buster.tools.spec import ToolSpec


def test_registry_loads_packs():
    reg = get_registry()
    assert len(reg.all()) >= 15
    assert "core.now" in {t.id for t in reg.all()}


def test_tool_permission_metadata():
    reg = get_registry()
    sys_check = reg.get("system.check")
    assert sys_check.risk_level == 0
    assert sys_check.permission == "system.read"


@pytest.mark.asyncio
async def test_tool_validates_arguments():
    reg = get_registry()
    # network.resolve_dns requires a 'host' arg; invoking with junk should raise.
    with pytest.raises(Exception):
        await reg.invoke("network.resolve_dns", {"not_host": 1})


@pytest.mark.asyncio
async def test_tool_invoke_ok():
    reg = get_registry()
    res = await reg.invoke("core.now", {})
    assert res.iso


def test_report_markdown_labels_findings():
    r = Report(
        id="r1", title="T", slug=slugify("T"),
        findings=[Finding(statement="X", support="supported", sources=["s1"])],
        sources=[ReportSource(url="http://a", title="A")],
    )
    md = r.to_markdown()
    assert "[Supported]" in md
    assert "http://a" in md


def test_report_store_versions():
    store = get_report_store()
    rid = store.new_id()
    r = Report(id=rid, title="V", slug="v")
    store.save(r)
    store.save(r)  # second save bumps version
    meta = store.get_meta(rid)
    assert meta["version"] == 2
