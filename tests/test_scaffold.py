"""Microservice codegen + Forge marketplace scaffolding (MIT-clean, native)."""

import pytest

from buster.scaffold import (
    ScaffoldPlan,
    adapt_to_marketplace,
    new_forge_app,
    scaffold_fastapi_module,
)


def test_scaffold_generates_runnable_module(tmp_path):
    out = tmp_path / "svc"
    res = scaffold_fastapi_module(
        ScaffoldPlan(module_name="Inventory", models=["product", "warehouse"],
                     output_dir=str(out)))
    assert set(res.files_written) >= {"main.py", "requirements.txt", "run.sh", "README.md"}
    main = (out / "main.py").read_text()
    # CRUD routes for each model + a health check.
    assert "/products" in main and "/warehouses" in main
    assert "class Product(Base)" in main and "class Warehouse(Base)" in main
    assert 'title="Inventory"' in main


def test_scaffold_refuses_nonempty_dir(tmp_path):
    (tmp_path / "existing.txt").write_text("x")
    with pytest.raises(FileExistsError):
        scaffold_fastapi_module(ScaffoldPlan(module_name="M", models=["a"],
                                             output_dir=str(tmp_path)))


def test_scaffold_force_allows_nonempty(tmp_path):
    (tmp_path / "existing.txt").write_text("x")
    res = scaffold_fastapi_module(
        ScaffoldPlan(module_name="M", models=["a"], output_dir=str(tmp_path)), force=True)
    assert "main.py" in res.files_written
    assert (tmp_path / "existing.txt").exists()  # pre-existing file untouched


def test_scaffold_generated_code_is_valid_python(tmp_path):
    import ast

    out = tmp_path / "svc"
    scaffold_fastapi_module(ScaffoldPlan(module_name="Svc", models=["thing"],
                                         output_dir=str(out)))
    ast.parse((out / "main.py").read_text())  # raises SyntaxError if broken


def test_forge_adapt_is_additive_and_nondestructive(tmp_path):
    # An existing "app" file must never be touched.
    app = tmp_path / "app.py"
    app.write_text("print('hello')\n")
    before = app.read_text()
    res = adapt_to_marketplace(str(tmp_path), "My App", "desc", "starter")
    assert "BUILDLY.yaml" in res.files_written
    assert (tmp_path / ".ai" / "AGENT_POLICY.md").exists()
    assert app.read_text() == before  # untouched


def test_forge_adapt_skips_existing_manifest(tmp_path):
    (tmp_path / "BUILDLY.yaml").write_text("id: keep-me\n")
    res = adapt_to_marketplace(str(tmp_path), "X")
    assert "BUILDLY.yaml" in res.files_skipped
    assert (tmp_path / "BUILDLY.yaml").read_text() == "id: keep-me\n"


def test_new_forge_app(tmp_path):
    out = tmp_path / "newapp"
    res = new_forge_app(str(out), "New App", "a new forge app")
    assert "README.md" in res.files_written
    assert (out / "BUILDLY.yaml").exists()
    assert res.manifest_id == "new-app"


def test_forge_skills_present():
    from buster.skills import get_skill_registry

    ids = {s.id for s in get_skill_registry().all()}
    assert {"new-forge-app", "adapt-to-marketplace"} <= ids
