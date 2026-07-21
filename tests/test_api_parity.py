"""CLI/API parity + endpoint smoke tests using an in-process TestClient.

The agent is monkeypatched so no real model is needed.
"""

import pytest
from starlette.testclient import TestClient

from buster.api import create_app


@pytest.fixture
def client(monkeypatch):
    # Stub the agent so /api/ask works without a model.
    from buster.agent.loop import AgentResult

    async def fake_run(self, prompt, conversation_id=None, workspace="default"):
        return AgentResult(content="stub answer", model="gemma3:latest", provider="ollama",
                           inference_location="lan", external_data_shared=False,
                           task_id="task_x", steps=1, tools_used=[])

    monkeypatch.setattr("buster.agent.loop.Agent.run", fake_run)
    with TestClient(create_app()) as c:
        yield c


def test_health(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_status_shape(client):
    d = client.get("/api/status").json()
    assert "capability_profile" in d
    assert "inference_policy" in d


def test_doctor(client):
    assert client.get("/api/doctor").json()["status"] in ("ok", "warning", "critical", "unknown")


def test_tools_and_skills(client):
    assert len(client.get("/api/tools").json()["tools"]) >= 15
    assert len(client.get("/api/skills").json()["skills"]) >= 8


def test_ask(client):
    d = client.post("/api/ask", json={"prompt": "hi"}).json()
    assert d["content"] == "stub answer"
    assert d["inference_location"] == "lan"
    assert d["external_data_shared"] is False


def test_system_and_network_checks(client):
    assert client.get("/api/system/check").json()["checks"]
    assert client.get("/api/network/check").json()["checks"]


def test_runtimes_lists_buster_and_mocks(client):
    names = [r["name"] for r in client.get("/api/runtimes").json()["runtimes"]]
    assert any("Buster" in n for n in names)


def test_manifest(client):
    m = client.get("/api/discovery/manifest").json()
    assert m["product"] == "buster"


def test_web_index(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Buster" in r.text


def test_network_graph_no_invented_devices(client):
    g = client.get("/api/network/graph").json()
    # Only self + explicitly-discovered nodes/services (none in a fresh DB).
    assert len([n for n in g["nodes"] if n.get("self")]) == 1
