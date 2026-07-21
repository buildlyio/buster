from buster.models.capability import detect_capabilities
from buster.prompts import get_prompts
from buster.prompts.service import PromptRecord


def test_capability_detection():
    prof = detect_capabilities()
    assert prof.platform in ("macos", "linux")
    assert prof.memory_gb > 0
    assert prof.recommended_model_class


def test_prompt_save_and_search():
    svc = get_prompts()
    svc.save(PromptRecord(id="", title="Implement local discovery",
                          original_prompt="build LCDP", tags=["discovery"]))
    results = svc.search("discovery")
    assert results
    assert results[0].visibility == "private"  # default


def test_prompt_redacts_secrets():
    svc = get_prompts()
    rec = svc.save(PromptRecord(id="", title="X",
                                source={"api_key": "sk-secret", "model": "gemma3"}))
    stored = svc.get(rec.id)
    assert stored.source["api_key"] == "***redacted***"
    assert stored.source["model"] == "gemma3"


def test_prompt_link():
    svc = get_prompts()
    rec = svc.save(PromptRecord(id="", title="Y"))
    svc.link(rec.id, "features", "feat_lcdp")
    assert "feat_lcdp" in svc.get(rec.id).linked_items["features"]
