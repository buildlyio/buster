import time

from buster.cache import get_cache
from buster.cache.manager import NS_TEMP, NS_WEB


def test_put_get_value():
    c = get_cache()
    c.put(NS_WEB, "k1", value={"a": 1})
    hit = c.get(NS_WEB, "k1")
    assert hit["value"] == {"a": 1}


def test_put_get_content():
    c = get_cache()
    c.put(NS_WEB, "k2", content=b"hello")
    hit = c.get(NS_WEB, "k2")
    assert hit["content"] == b"hello"


def test_expiry():
    c = get_cache()
    c.put(NS_TEMP, "k3", value=1, ttl=1)
    assert c.get(NS_TEMP, "k3") is not None
    time.sleep(1.1)
    assert c.get(NS_TEMP, "k3") is None


def test_clear_namespace_is_scoped():
    c = get_cache()
    c.put(NS_WEB, "w", value=1)
    c.put(NS_TEMP, "t", value=1)
    c.clear_namespace(NS_WEB)
    assert c.get(NS_WEB, "w") is None
    assert c.get(NS_TEMP, "t") is not None


def test_mem_lru():
    c = get_cache()
    c.mem_set("x", 42)
    assert c.mem_get("x") == 42
