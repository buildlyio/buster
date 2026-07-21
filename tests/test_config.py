from buster.config import BusterConfig, load_config, save_config


def test_defaults_valid():
    c = BusterConfig()
    assert c.server.host == "127.0.0.1"
    assert c.server.lan_access is False
    assert c.inference.policy == "local_first_ask_external"
    assert c.base_url == "http://127.0.0.1:8765"


def test_roundtrip(tmp_path):
    c = BusterConfig()
    c.inference.default_model = "gemma3:latest"
    c.discovery.service_urls.append("http://x.local")
    path = tmp_path / "config.toml"
    save_config(c, path)
    loaded = load_config(path)
    assert loaded.inference.default_model == "gemma3:latest"
    assert loaded.discovery.service_urls == ["http://x.local"]


def test_missing_file_returns_defaults(tmp_path):
    assert load_config(tmp_path / "nope.toml").server.port == 8765
