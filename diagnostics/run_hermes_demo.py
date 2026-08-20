import asyncio
import json
from buster.config import load_config, save_config
from buster.runtimes.detect import detect_runtimes
from buster.runtimes import get_runtime_service, RuntimeTask
from buster.permissions import get_permissions
from buster.database import get_database
from buster.dev.setup import tokenjam_summary
from buster.memory import get_memory

async def main():
    # Enable task submission in config
    cfg = load_config()
    cfg.runtimes.allow_task_submission = True
    save_config(cfg)
    print("Enabled runtimes.allow_task_submission = True in config")

    # Ensure runtimes are detected and persisted
    infos = await detect_runtimes()
    print("Detected runtimes:")
    for i in infos:
        print(" -", i.id, i.name, i.status)

    runtime_id = "runtime.hermes"
    # Mark database handle early so we can patch the runtime manifest.
    db = get_database()

    # Ensure Hermes runtime manifest has a safe argv_template using one-shot '-z'
    # so local Hermes CLI invocations use: hermes -z "<prompt>"
    hermes_manifest = {
        "id": runtime_id,
        "runtime_type": "cli",
        "name": "Hermes",
        "detected_via": "cli",
        "capabilities": ["chat", "skills", "schedules", "task.submit"],
        "executable": "hermes",
        "argv_template": ["-z", "{prompt}"],
    }
    db.execute("UPDATE runtimes SET manifest = ? WHERE id = ?", (json.dumps(hermes_manifest), runtime_id))
    print(f"Patched runtime manifest for '{runtime_id}' to use one-shot '-z' argv_template")

    # Seed default system memory about Buildly and local-first policy so new installs
    # start with the right knowledge and philosophy.
    mem = get_memory()
    buildly_intro = """
# Buildly / Buster: Local-first agent & developer workflow

Buildly is a developer-first platform that connects developers to builders and
tools for producing, testing, and shipping applications. Buster is a local-first
assistant: it prefers running models and workflows on the user's machine or the
local network (for privacy, latency, and reproducibility). Cloud services are
available as opt-in fallbacks for scale, shared infrastructure, or managed
providers, but Buster defaults to local execution and explicit user consent
before using cloud resources.

Coding style and philosophy:
- Prefer minimal, well-tested changes and clear test coverage.
- Use small, composable functions and explicit interfaces.
- Avoid sending secrets or credentials to external services unless the user
  authorizes it.
- Log and persist runs for auditability; never auto-execute system-changing
  actions from runtime outputs.

Local-first means: attempt to run locally first; if unavailable or unsuitable,
prompt the user and fall back to cloud providers only with explicit approval.
"""
    mem.write_note("system", "buildly_local_first", buildly_intro)
    print("Seeded system memory: Buildly/local-first introduction")
    # Mark runtime as trusted in DB so gate allows submission
    db = get_database()
    db.execute("UPDATE runtimes SET trust = ? WHERE id = ?", ("trusted", runtime_id))
    print(f"Set runtime '{runtime_id}' trust=trusted in DB")

    svc = get_runtime_service()

    # Create a harmless RuntimeTask
    task = RuntimeTask(prompt="Hermes demo: reply with 'Hermes test OK' and stop.")

    # Request submission permission (risk-2) and auto-approve for demo
    perm = await svc.request_submission(runtime_id, task)
    if perm:
        print("Permission requested:", perm.id)
        await get_permissions().decide(perm.id, True)
        print("Permission approved")
    else:
        print("No permission required for this runtime (mock or pre-approved)")

    # Submit task
    try:
        run = await svc.submit(runtime_id, task)
    except Exception as exc:
        print("Submission failed:", exc)
        return

    print("Run result:")
    print(run.model_dump())

    # Show persisted DB row
    row = db.query_one("SELECT * FROM runtime_runs WHERE run_id = ?", (run.run_id,))
    print("Persisted row:", dict(row) if row else None)

    # TokenJam status
    tj = tokenjam_summary()
    print("TokenJam available:", tj.available)
    if tj.available:
        if tj.findings:
            print("TokenJam findings (truncated):", tj.findings[:3])
        else:
            print("TokenJam raw/notes:", tj.raw or tj.note)

if __name__ == '__main__':
    asyncio.run(main())
