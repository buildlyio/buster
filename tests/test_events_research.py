import pytest

from buster.events import Event, EventType, get_event_bus


@pytest.mark.asyncio
async def test_event_persist_and_recent():
    bus = get_event_bus()
    await bus.publish(Event(type=EventType.TASK_CREATED, task_id="t1", title="hi"))
    recent = bus.recent(task_id="t1")
    assert recent
    assert recent[-1].type == EventType.TASK_CREATED


@pytest.mark.asyncio
async def test_event_sse_frame():
    e = Event(type=EventType.MODEL_SELECTED, title="ollama:gemma3")
    frame = e.sse()
    assert frame.startswith("event: model.selected")
    assert "gemma3" in frame


@pytest.mark.asyncio
async def test_subscribe_receives_events():
    bus = get_event_bus()
    async with bus.subscribe() as q:
        await bus.publish(Event(type=EventType.ALERT_CREATED, title="disk"))
        e = await q.get()
        assert e.type == EventType.ALERT_CREATED


@pytest.mark.asyncio
async def test_research_workflow_mocked(monkeypatch):
    """Research pipeline should build a report from mocked search+fetch, no net."""
    from buster.research import search as search_mod
    from buster.research import fetch as fetch_mod
    from buster.research.fetch import FetchedPage
    from buster.research.search import SearchResultItem

    class FakeProvider:
        name = "fake"

        async def search(self, query, limit=8):
            return [SearchResultItem(title="Src A", url="http://a.example", snippet="claim a"),
                    SearchResultItem(title="Src B", url="http://b.example", snippet="claim b")]

    async def fake_fetch(url, use_cache=True):
        return FetchedPage(url=url, status=200, title="Fetched " + url, text="body text",
                           content_hash="h")

    monkeypatch.setattr(search_mod, "get_search_provider", lambda name="": FakeProvider())
    monkeypatch.setattr("buster.research.workflow.get_search_provider", lambda name="": FakeProvider())
    monkeypatch.setattr("buster.research.workflow.fetch_url", fake_fetch)

    from buster.research.workflow import run_quick_research

    result = await run_quick_research("test question")
    assert result["sources"] == 2

    from buster.reports import get_report_store
    md = get_report_store().get_markdown(result["report_id"])
    assert "Single-source claim" in md
    assert "not independently verified" in md
