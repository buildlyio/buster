"""Text-to-speech speaker with graceful provider fallback.

Providers, in order of preference at runtime:
  * pyttsx3 — offline, cross-platform, no GPU (default). Optional dependency:
    if not installed, speaking degrades to a no-op with a clear reason.
  * say     — macOS built-in `say` command (no deps).
  * riva    — neural TTS server (opt-in); Phase-1 support is best-effort.
  * none    — muted.

Speaking is best-effort and never raises into the caller: a failed/absent
engine returns a SpeakResult(ok=False, ...) so the assistant keeps working.
"""

from __future__ import annotations

import shutil
import subprocess
from datetime import datetime
from functools import lru_cache

from pydantic import BaseModel

from buster.config import load_config
from buster.voice.catalog import get_voice


class SpeakResult(BaseModel):
    ok: bool
    provider: str = ""
    voice: str = ""
    detail: str = ""


def _in_quiet_hours(spec: str) -> bool:
    """spec is 'HH:MM-HH:MM' in local time; handles ranges crossing midnight."""
    if not spec or "-" not in spec:
        return False
    try:
        start_s, end_s = spec.split("-", 1)
        now = datetime.now().time()
        sh, sm = (int(x) for x in start_s.split(":"))
        eh, em = (int(x) for x in end_s.split(":"))
        start = sh * 60 + sm
        end = eh * 60 + em
        cur = now.hour * 60 + now.minute
        if start <= end:
            return start <= cur < end
        return cur >= start or cur < end   # wraps past midnight
    except Exception:  # noqa: BLE001
        return False


class Speaker:
    def available(self) -> bool:
        cfg = load_config().voice
        if not cfg.enabled or cfg.provider == "none":
            return False
        if cfg.provider == "pyttsx3":
            # pyttsx3, or the macOS `say` zero-install fallback.
            return _pyttsx3_available() or shutil.which("say") is not None
        if cfg.provider == "say":
            return shutil.which("say") is not None
        if cfg.provider == "riva":
            return True  # attempted at speak time
        return False

    def speak(self, text: str, *, respect_quiet: bool = True) -> SpeakResult:
        cfg = load_config().voice
        if not cfg.enabled or cfg.provider == "none":
            return SpeakResult(ok=False, provider="none", detail="Voice disabled.")
        if respect_quiet and _in_quiet_hours(cfg.quiet_hours):
            return SpeakResult(ok=False, provider=cfg.provider, detail="Quiet hours.")
        voice = get_voice(cfg.voice)
        text = (text or "").strip()
        if not text:
            return SpeakResult(ok=False, detail="Empty text.")

        if cfg.provider == "pyttsx3":
            res = self._speak_pyttsx3(text, voice, cfg.rate)
            # Zero-install fallback: pyttsx3 missing but macOS `say` present.
            if not res.ok and "not installed" in res.detail and shutil.which("say"):
                return self._speak_say(text, voice, cfg.rate)
            return res
        if cfg.provider == "say":
            return self._speak_say(text, voice, cfg.rate)
        if cfg.provider == "riva":
            return self._speak_riva(text, voice, cfg)
        return SpeakResult(ok=False, provider=cfg.provider, detail="Unknown provider.")

    def _speak_pyttsx3(self, text, voice, rate) -> SpeakResult:
        try:
            import pyttsx3
        except Exception:  # noqa: BLE001
            return SpeakResult(ok=False, provider="pyttsx3",
                               detail="pyttsx3 not installed (pip install pyttsx3).")
        try:
            engine = pyttsx3.init()
            engine.setProperty("rate", rate)
            if voice.pyttsx3_hint:
                for v in engine.getProperty("voices"):
                    if voice.pyttsx3_hint.lower() in (v.name or "").lower() \
                       or voice.pyttsx3_hint.lower() in (v.id or "").lower():
                        engine.setProperty("voice", v.id)
                        break
            engine.say(text)
            engine.runAndWait()
            return SpeakResult(ok=True, provider="pyttsx3", voice=voice.name)
        except Exception as exc:  # noqa: BLE001
            return SpeakResult(ok=False, provider="pyttsx3", detail=str(exc)[:160])

    def _speak_say(self, text, voice, rate) -> SpeakResult:
        if not shutil.which("say"):
            return SpeakResult(ok=False, provider="say", detail="'say' not available.")
        args = ["say", "-r", str(rate)]
        if voice.say_voice:
            args += ["-v", voice.say_voice]
        try:
            subprocess.run([*args, text], timeout=60, check=False)
            return SpeakResult(ok=True, provider="say", voice=voice.name)
        except Exception as exc:  # noqa: BLE001
            return SpeakResult(ok=False, provider="say", detail=str(exc)[:160])

    def _speak_riva(self, text, voice, cfg) -> SpeakResult:
        # Best-effort: a full Riva/PersonaPlex client is opt-in and heavy. Until
        # wired, fall back to pyttsx3 so the user still hears something.
        res = self._speak_pyttsx3(text, voice, cfg.rate)
        res.detail = ("Riva client not yet wired; used pyttsx3. "
                      "Set provider=pyttsx3 to silence this note.") if res.ok else res.detail
        return res


@lru_cache(maxsize=1)
def _pyttsx3_available() -> bool:
    try:
        import pyttsx3  # noqa: F401

        return True
    except Exception:  # noqa: BLE001
        return False


@lru_cache(maxsize=1)
def get_speaker() -> Speaker:
    return Speaker()


def speak(text: str, respect_quiet: bool = True) -> SpeakResult:
    return get_speaker().speak(text, respect_quiet=respect_quiet)
