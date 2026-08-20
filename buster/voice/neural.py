"""Neural TTS client for a PersonaPlex / moshi-style WebSocket server.

Protocol mirrors the NullRecords audiobook pipeline (thanks!): connect to a
``wss://host:port`` endpoint, send ``{"type":"synthesize", text, persona,
voice_prompt, sample_rate}``, receive binary PCM/WAV chunks until a
``{"type":"done"}`` message (or ``{"type":"error"}``). Self-signed certs on
localhost are tolerated.

Buster uses this only when ``voice.provider = "riva"`` (neural) AND the server
is reachable; otherwise the speaker falls back to pyttsx3 / ``say``. Synthesis
returns WAV bytes; ``synthesize_and_play`` writes a temp WAV and plays it with
the platform audio player. Everything is best-effort and never raises into the
caller — a failure returns ``None`` so talk-back degrades gracefully.

``websockets`` is an optional dependency; if it's missing this reports so and
the caller falls back.
"""

from __future__ import annotations

import json
import shutil
import ssl
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

_SAMPLE_RATE = 24000  # PersonaPlex default


class NeuralTTSResult:
    def __init__(self, ok: bool, wav_path: str = "", detail: str = "") -> None:
        self.ok = ok
        self.wav_path = wav_path
        self.detail = detail


async def synthesize(
    text: str, server_url: str, *, persona: str | None = None,
    voice_prompt: str | None = None, sample_rate: int = _SAMPLE_RATE,
    timeout: float = 30.0,
) -> bytes | None:
    """Return raw audio bytes from the neural server, or None on any failure."""
    try:
        import asyncio

        import websockets
    except Exception:  # noqa: BLE001
        return None

    ssl_ctx = None
    if server_url.startswith("wss"):
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

    try:
        async with websockets.connect(server_url, ssl=ssl_ctx, open_timeout=8) as ws:
            await ws.send(json.dumps({
                "type": "synthesize", "text": text, "persona": persona,
                "voice_prompt": voice_prompt, "sample_rate": sample_rate,
            }))
            chunks: list[bytes] = []
            while True:
                try:
                    resp = await asyncio.wait_for(ws.recv(), timeout=timeout)
                except TimeoutError:
                    break
                if isinstance(resp, bytes | bytearray):
                    chunks.append(bytes(resp))
                else:
                    data = json.loads(resp)
                    if data.get("type") == "done":
                        break
                    if data.get("type") == "error":
                        return None
            return b"".join(chunks) if chunks else None
    except Exception:  # noqa: BLE001
        return None


async def health(server_url: str, timeout: float = 5.0) -> bool:
    """Best-effort reachability check for the neural server."""
    try:
        import websockets
    except Exception:  # noqa: BLE001
        return False
    ssl_ctx = None
    if server_url.startswith("wss"):
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE
    try:
        async with websockets.connect(server_url, ssl=ssl_ctx, open_timeout=timeout):
            return True
    except Exception:  # noqa: BLE001
        return False


def _wrap_wav(raw: bytes, sample_rate: int) -> str:
    """Write audio bytes to a temp WAV. If `raw` is already a WAV (RIFF header),
    keep it; otherwise treat it as 16-bit mono PCM and add a header."""
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp_path = tmp.name
    tmp.close()
    if raw[:4] == b"RIFF":
        Path(tmp_path).write_bytes(raw)
        return tmp_path
    with wave.open(tmp_path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(raw)
    return tmp_path


def _player_cmd(path: str) -> list[str] | None:
    if sys.platform == "darwin" and shutil.which("afplay"):
        return ["afplay", path]
    for p in ("paplay", "aplay", "ffplay"):
        if shutil.which(p):
            return ([p, "-nodisp", "-autoexit", path] if p == "ffplay" else [p, path])
    return None


async def synthesize_and_play(
    text: str, server_url: str, *, persona: str | None = None,
    voice_prompt: str | None = None, sample_rate: int = _SAMPLE_RATE,
) -> NeuralTTSResult:
    """Synthesize via the neural server and play it locally. Best-effort."""
    raw = await synthesize(text, server_url, persona=persona,
                           voice_prompt=voice_prompt, sample_rate=sample_rate)
    if not raw:
        return NeuralTTSResult(ok=False, detail="neural server unreachable or no audio")
    try:
        wav_path = _wrap_wav(raw, sample_rate)
    except Exception as exc:  # noqa: BLE001
        return NeuralTTSResult(ok=False, detail=f"wav error: {exc}")
    cmd = _player_cmd(wav_path)
    if cmd is None:
        return NeuralTTSResult(ok=True, wav_path=wav_path,
                               detail="synthesized but no audio player found")
    try:
        subprocess.run(cmd, timeout=120, check=False)
    except Exception as exc:  # noqa: BLE001
        return NeuralTTSResult(ok=False, wav_path=wav_path, detail=f"playback error: {exc}")
    finally:
        Path(wav_path).unlink(missing_ok=True)
    return NeuralTTSResult(ok=True, detail="neural TTS played")
