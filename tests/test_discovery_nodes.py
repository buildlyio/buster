from buster.discovery import build_self_manifest, get_discovery
from buster.discovery.lcdp import LCDPManifest


def test_self_manifest():
    m = build_self_manifest()
    assert m.product == "buster"
    assert m.schema_ == "lcdp/v1"
    assert "research.web" in m.capabilities


def test_manifest_parse_service_vs_node():
    disco = get_discovery()
    svc = LCDPManifest.model_validate({
        "schema": "lcdp/v1", "id": "launchpad.local", "name": "Launchpad",
        "product": "launchpad", "capabilities": ["process.status"],
    })
    disco.record_service(svc)
    assert any(s["id"] == "launchpad.local" for s in disco.list_services())


def test_node_trust_decision():
    disco = get_discovery()
    node = LCDPManifest.model_validate({
        "schema": "lcdp/v1", "id": "buster.remote", "name": "Buster remote",
        "product": "buster",
    })
    disco.record_node(node)
    disco.set_node_trust("buster.remote", "trusted")
    n = next(n for n in disco.list_nodes() if n["id"] == "buster.remote")
    assert n["trust"] == "trusted"


def test_default_trust_is_discovered():
    disco = get_discovery()
    svc = LCDPManifest.model_validate({"schema": "lcdp/v1", "id": "s2", "name": "S2"})
    disco.record_service(svc)
    s = next(s for s in disco.list_services() if s["id"] == "s2")
    assert s["trust"] == "discovered"  # never auto-trusted
