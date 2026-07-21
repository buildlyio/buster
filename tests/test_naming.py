"""LAN naming: per-host names so multiple Busters coexist on one network."""

from buster.config import load_config, save_config
from buster.discovery import naming
from buster.discovery.advertise import _mdns_host


def _set(domain=None, node_name=None, alias=None):
    c = load_config()
    if domain is not None:
        c.server.domain = domain
    if node_name is not None:
        c.server.node_name = node_name
    if alias is not None:
        c.server.advertise_alias = alias
    save_config(c)


def test_primary_name_is_per_host():
    _set(domain="buster.home", node_name="alderaan")
    assert naming.primary_name() == "alderaan.buster.home"


def test_alias_present_by_default():
    _set(domain="buster.home", node_name="alderaan", alias=True)
    assert naming.all_names() == ["alderaan.buster.home", "buster.home"]


def test_alias_can_be_disabled():
    _set(domain="buster.home", node_name="macbook", alias=False)
    assert naming.all_names() == ["macbook.buster.home"]


def test_node_name_derives_from_hostname_when_blank():
    _set(domain="buster.local", node_name="")
    # Derived slug is non-empty and DNS-safe.
    slug = naming.node_slug()
    assert slug and all(ch.isalnum() or ch == "-" for ch in slug)


def test_two_nodes_get_distinct_names():
    _set(domain="buster.home", node_name="alderaan")
    a = naming.primary_name()
    _set(node_name="pi5")
    b = naming.primary_name()
    assert a != b
    assert a == "alderaan.buster.home" and b == "pi5.buster.home"


def test_needs_manual_dns_only_for_non_local():
    _set(domain="buster.home")
    assert naming.needs_manual_dns() is True
    _set(domain="buster.local")
    assert naming.needs_manual_dns() is False


def test_dns_records_empty_for_local():
    _set(domain="buster.local", node_name="x")
    assert naming.dns_records() == []


def test_dns_records_for_home_cover_all_names():
    _set(domain="buster.home", node_name="alderaan", alias=True)
    recs = naming.dns_records(ip="192.168.1.50")
    names = [n for n, _ in recs]
    assert "alderaan.buster.home" in names
    assert "buster.home" in names
    assert all(ip == "192.168.1.50" for _, ip in recs)


def test_mdns_host_maps_home_to_local():
    _set(domain="buster.home", node_name="alderaan")
    assert _mdns_host("alderaan.buster.home") == "alderaan.buster.local"
    assert _mdns_host("buster.home") == "buster.local"
    assert _mdns_host("alderaan.buster.local") == "alderaan.buster.local"
