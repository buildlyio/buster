"""Progressive enforcement settings (Phase 4).

Per the spec, an adopted app defaults to OBSERVE and can be dialed up:
  observe → record → guide → enforce_new_work → full_enforcement

Stored per-repo as Git-trackable .buildly/enforcement.yaml. This module owns the
setting + an explanation of what each level changes; the actual enforcement
CHECKS (docs required, contracts required, architecture violations) belong to
bb-agent-manager's validation engine — Buster stores the policy and explains it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from buster.buildly.protocol import EnforcementMode

_FILE = ".buildly/enforcement.yaml"

# What each level changes, in plain language (shown by CLI/web).
LEVEL_EXPLANATIONS = {
    "observe": "Watch only. Nothing is required or blocked. (Default for adopted apps.)",
    "record": "Record findings and decisions, but don't require or block anything.",
    "guide": "Suggest docs/contracts on new work; warn, never block.",
    "enforce_new_work": "Require docs/feature contracts for NEW code; existing code is baselined.",
    "full_enforcement": "Require docs/contracts everywhere; new architecture violations fail.",
}

# The detailed policy each mode implies (mirrors the spec's example config).
def _policy_for(mode: str) -> dict:
    require_new = mode in ("enforce_new_work", "full_enforcement")
    require_all = mode == "full_enforcement"
    return {
        "mode": mode,
        "documentation": {
            "existing_code": "require" if require_all else "warn",
            "new_code": "require" if require_new else ("warn" if mode == "guide" else "optional"),
        },
        "feature_contracts": {
            "existing_code": "require" if require_all else "optional",
            "new_code": "require" if require_new else "optional",
        },
        "architecture": {
            "existing_violations": "fail" if require_all else "baseline",
            "new_violations": "fail" if require_new else "warn",
        },
    }


def get_enforcement(repo: str) -> dict:
    path = Path(repo).expanduser() / _FILE
    mode = EnforcementMode.OBSERVE.value
    if path.exists():
        try:
            data = yaml.safe_load(path.read_text()) or {}
            mode = str(data.get("mode", mode))
        except Exception:  # noqa: BLE001
            pass
    return {
        "mode": mode,
        "explanation": LEVEL_EXPLANATIONS.get(mode, ""),
        "policy": _policy_for(mode),
        "levels": [
            {"mode": m, "explanation": LEVEL_EXPLANATIONS[m]}
            for m in [e.value for e in EnforcementMode]
        ],
    }


def set_enforcement(repo: str, mode: str) -> dict:
    valid = {e.value for e in EnforcementMode}
    if mode not in valid:
        return {"ok": False, "error": f"invalid mode '{mode}'. Choose from {sorted(valid)}."}
    d = Path(repo).expanduser() / ".buildly"
    d.mkdir(parents=True, exist_ok=True)
    (d / "enforcement.yaml").write_text(yaml.safe_dump(_policy_for(mode), sort_keys=False))
    return {"ok": True, **get_enforcement(repo)}
