import asyncio
from buster.buildly.mcp_client import get_mcp_client
from buster.runtimes.detect import detect_runtimes

async def main():
    client = get_mcp_client()
    print("MCP available:", client.available)
    try:
        state = await client.auth_state()
        print("MCP auth state:", state)
    except Exception as e:
        print("MCP auth probe error:", repr(e))
    runtimes = await detect_runtimes()
    if not runtimes:
        print("No runtimes detected.")
    for r in runtimes:
        print(r.runtime_type, r.name, r.detected_via, r.status)

if __name__ == '__main__':
    asyncio.run(main())
