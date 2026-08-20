import asyncio
import sys

from buster import __version__
from buster.config import load_config
from buster.runtimes.detect import detect_runtimes
from buster.buildly.mcp_client import get_mcp_client
from buster.memory import get_memory


async def main():
    print("Buster version:", __version__)
    cfg = load_config()
    print("buildly.mcp_url:", cfg.buildly.mcp_url, "mode:", cfg.buildly.mode)

    runtimes = await detect_runtimes()
    print("Detected runtimes:")
    for r in runtimes:
        print(" -", r.id, r.runtime_type, r.status)

    client = get_mcp_client()
    print("MCP available:", client.available)
    try:
        state = await client.auth_state()
        print("MCP auth state:", state)
    except Exception as exc:
        print("MCP auth_state error:", repr(exc))

    mem = get_memory()
    hits = mem.search("Buildly", limit=5)
    print("Memory search for 'Buildly' hits:", [h.model_dump() for h in hits])


if __name__ == '__main__':
    asyncio.run(main())
