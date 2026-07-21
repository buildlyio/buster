from buster.memory import get_memory


def test_write_and_search():
    mem = get_memory()
    mem.write_note("projects", "buster",
                   "# Buster\n\n## Discovery\n\nLocal Capability Discovery Protocol finds services.\n")
    hits = mem.search("discovery protocol")
    assert hits, "expected FTS hit"
    assert any("Discovery" in h.heading_path or "Discovery" in h.text for h in hits)


def test_sections_split_by_heading():
    mem = get_memory()
    mem.write_note("system", "notes", "# A\n\ntext a\n\n## B\n\ntext b\n")
    hits = mem.search("text")
    headings = {h.heading_path for h in hits}
    assert "A" in headings
    assert "A > B" in headings


def test_search_handles_punctuation():
    mem = get_memory()
    mem.write_note("personal", "p", "# P\n\nquestion? with: punctuation!\n")
    # Should not raise despite FTS-special characters.
    assert mem.search("question? punctuation!") is not None
