"""Files tool pack: read Buster-owned files safely (no arbitrary FS write).

Reads are constrained to Buster's own data/home directories to avoid becoming a
generic file-exfiltration tool.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel

from buster.config import get_paths
from buster.tools.registry import tool


class ReadArgs(BaseModel):
    path: str
    max_bytes: int = 100_000


class ReadResult(BaseModel):
    path: str
    text: str
    truncated: bool
    untrusted: bool = True  # file contents are untrusted data, not instructions


def _within_home(p: Path) -> bool:
    home = get_paths().home.resolve()
    try:
        p.resolve().relative_to(home)
        return True
    except ValueError:
        return False


@tool(
    id="files.read",
    description="Read a UTF-8 text file within Buster's data directory.",
    pack="files",
    permission="read",
    untrusted_output=True,
)
async def read_file(args: ReadArgs) -> ReadResult:
    p = Path(args.path).expanduser()
    if not _within_home(p):
        raise PermissionError("files.read is restricted to Buster's data directory")
    data = p.read_bytes()[: args.max_bytes + 1]
    truncated = len(data) > args.max_bytes
    text = data[: args.max_bytes].decode("utf-8", errors="replace")
    return ReadResult(path=str(p), text=text, truncated=truncated)
