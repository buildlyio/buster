from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

from buster.buildly.protocol import (
    AdoptionInventory,
    AdoptionReport,
    FeatureContract,
    InferredStatement,
    StatementStatus,
)


AppType = Literal["service", "web", "cli", "docs", "monorepo", "library", "unknown"]


class AppTypeClassifier:
    """Heuristic repo classifier for Buildly adoption workflows."""

    _SERVICE = re.compile(r"(^|/)(src|app|pkg|cmd)/(.*)?$|pyproject\.toml$|setup\.py$|setup\.cfg$")
    _WEB = re.compile(r"(^|/)(frontend|public|static|web|www|client|next\.config|vite\.config|webpack\.config|angular\.json|package\.json)$")
    _CLI = re.compile(r"(^|/)(cli|cmd|scripts)/(.*)?$|click|typer|argparse|commander|chalk")
    _DOCS = re.compile(r"(^|/)(docs|devdocs|documentation|wiki)/(.*)?$|\.md$|readme\.md$|mkdocs\.yml$|mkdocs\.yaml$|docusaurus\.config")
    _MONO = re.compile(r"(^|/)(packages|libs|modules|apps|services)/(.*)?$|pnpm-workspace\.yaml$|lerna\.json$|turbo\.json$|nx\.json$")
    _LIB = re.compile(r"(^|/)(lib|library|libraries)/(.*)?$|pypi\.org|crates\.io|library-name|package\.json$")
    _SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".buildly", "dist", "build", ".next", ".turbo"}

    def classify(self, repo_path: Path) -> AppType:
        entries = list(self._iter_files(repo_path))
        if not entries:
            return "unknown"

        scores: dict[AppType, int] = {
            "service": 0,
            "web": 0,
            "cli": 0,
            "docs": 0,
            "monorepo": 0,
            "library": 0,
            "unknown": 0,
        }
        for rel, name in entries:
            low = f"{rel}/{name}".lower()
            if self._SERVICE.search(low):
                scores["service"] += 2
            if self._WEB.search(low):
                scores["web"] += 2
            if self._CLI.search(low):
                scores["cli"] += 1
            if self._DOCS.search(low):
                scores["docs"] += 2
            if self._MONO.search(low):
                scores["monorepo"] += 3
            if self._LIB.search(low):
                scores["library"] += 1

            # special file signals
            if name == "pyproject.toml":
                scores["service"] += 2
            if name == "package.json":
                scores["web"] += 1
                scores["cli"] += 1
            if name in ("mkdocs.yml", "mkdocs.yaml", "docusaurus.config.js"):
                scores["docs"] += 3
            if name in ("lerna.json", "pnpm-workspace.yaml", "turbo.json", "nx.json"):
                scores["monorepo"] += 3

        best = max(scores.items(), key=lambda kv: kv[1])
        return best[0] if best[1] > 0 else "unknown"

    def _iter_files(self, repo_path: Path):
        max_files = 200
        count = 0
        for path in sorted(repo_path.rglob("*")):
            if not path.is_file():
                continue
            rel_parts = path.relative_to(repo_path).parts
            if any(part in self._SKIP_DIRS for part in rel_parts):
                continue
            yield "/".join(rel_parts[:-1]), path.name
            count += 1
            if count >= max_files:
                break
    
    def inventory(self, repo_path: Path) -> AdoptionInventory:
        """Lightweight inventory used for docs/binding generation."""
        frameworks: list[str] = []
        languages: list[str] = []
        apps_packages: list[str] = []
        api_routes: list[str] = []
        tests: list[str] = []
        docs: list[str] = []

        for rel, name in self._iter_files(repo_path):
            low = f"{rel}/{name}".lower() if rel else name.lower()

            if name == "pyproject.toml":
                languages.append("python")
                apps_packages.append(name)
            if name == "package.json":
                languages.append("javascript")
                apps_packages.append(name)
            if "fastapi" in low:
                frameworks.append("fastapi")
            if "django" in low:
                frameworks.append("django")
            if "flask" in low:
                frameworks.append("flask")
            if "react" in low:
                frameworks.append("react")
            if "vite" in low:
                frameworks.append("vite")
            if "/routes" in low and name.endswith(".py"):
                api_routes.append(f"{rel}/{name}")
            if "/tests" in low or "/test" in low:
                tests.append(f"{rel}/{name}")
            if rel.startswith("docs") or rel.startswith("devdocs"):
                docs.append(f"{rel}/{name}")
            if not rel and name in ("mkdocs.yml", "mkdocs.yaml", "docusaurus.config.js", "readthedocs.yml"):
                docs.append(name)

        return AdoptionInventory(
            frameworks=sorted(set(frameworks)),
            languages=sorted(set(languages)),
            apps_packages=apps_packages,
            api_routes=api_routes,
            tests=tests,
            existing_docs=docs,
        )


def build_adoption_report(repo_path: Path, labels: list[str] | None = None) -> AdoptionReport:
    """Build a minimal adoption report for an app type."""
    repo_name = repo_path.resolve().name
    labels = labels or [repo_name]
    classifier = AppTypeClassifier()
    app_type = classifier.classify(repo_path)
    inventory = classifier.inventory(repo_path)

    statements = [
        InferredStatement(id=f"s_{i}", text=text, status="inferred")
        for i, text in enumerate([
            f"App type inferred as `{app_type}`.",
            f"Primary languages: {', '.join(inventory.languages) or 'unknown'}.",
            f"Frameworks detected: {', '.join(inventory.frameworks) or 'none'}.",
        ])
    ]

    features = [
        FeatureContract(id="f_adoption", name="Buildly adoption",
                        description=f"Infer Buildly adoption metadata for {repo_name}.")
    ]

    return AdoptionReport(
        repository=str(repo_path),
        generated_at=_now(),
        app_type=app_type,
        inventory=inventory,
        proposed_features=features,
        statements=statements,
        output_dirs=[str(repo_path / ".buildly")],
    )


def write_binding(repo_path: Path, report: AdoptionReport) -> Path:
    """Write `.buildly/project.yaml` binding from an adoption report."""
    import yaml

    proj_dir = repo_path / ".buildly"
    proj_dir.mkdir(parents=True, exist_ok=True)
    path = proj_dir / "project.yaml"
    data = {
        "schema": "provisional/0",
        "repository": report.repository,
        "app_type": report.app_type,
        "languages": report.inventory.languages,
        "frameworks": report.inventory.frameworks,
        "proposed_features": [f.name for f in report.proposed_features],
        "status": "inferred",
    }
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


def write_adoption_docs(repo_path: Path, report: AdoptionReport) -> Path:
    """Write `devdocs/generated/adoption.md`."""
    out_dir = repo_path / "devdocs" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "adoption.md"
    lines = [
        f"# Adoption report: {report.repository}",
        "",
        "## Inventory",
        f"- languages: {', '.join(report.inventory.languages) or 'unknown'}",
        f"- frameworks: {', '.join(report.inventory.frameworks) or 'none'}",
        f"- apps/packages: {', '.join(report.inventory.apps_packages) or 'none'}",
        f"- api_routes: {len(report.inventory.api_routes)}",
        f"- tests: {len(report.inventory.tests)}",
        f"- docs: {len(report.inventory.existing_docs)}",
        "",
        "## Proposed features",
    ]
    for feature in report.proposed_features:
        lines.append(f"- {feature.name}: {feature.description}")
    lines += [
        "",
        "## Status",
        "- All statements are **inferred** until a human approves them.",
        "- No auto-merge. See `.ai/AGENT_POLICY.md`.",
    ]
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def _app_type_from_inventory(inventory: AdoptionInventory) -> str:
    langs = inventory.languages
    fws = inventory.frameworks
    apps = inventory.apps_packages or []
    has_web_signal = any(fw in fws for fw in ("react", "vite", "webpack")) or any(
        x.endswith("/package.json") for x in apps
    )
    has_python_service_signal = "python" in langs and any(fw in fws for fw in ("fastapi", "django", "flask"))

    if has_python_service_signal:
        return "service"
    if has_web_signal:
        return "web"
    if any(x in ("cli", "cmd", "scripts") or x.endswith("/scripts") for x in apps) or "typer" in fws or "click" in fws:
        return "cli"
    if len(inventory.existing_docs) >= 2 and not has_web_signal:
        return "docs"
    if len(apps) > 3:
        return "monorepo"
    if "javascript" in langs and not has_web_signal:
        return "library"
    return "unknown"


def _now() -> str:
    from datetime import UTC, datetime
    return datetime.now(UTC).astimezone().isoformat(timespec="seconds")
