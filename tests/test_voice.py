"""Voice: catalog, speaker fallback/gating, quiet hours, event→speech notifier."""

import pytest

from buster.config import load_config, save_config
from buster.voice import VOICE_CATALOG, catalog
from buster.voice import speaker as spk


def _voice(**kw):
    c = load_config()
    c.voice.enabled = kw.get("enabled", True)
    c.voice.provider = kw.get("provider", "say")
    c.voice.voice = kw.get("voice", "narrator")
    c.voice.quiet_hours = kw.get("quiet_hours", "")
    if "announce_events" in kw:
        c.voice.announce_events = kw["announce_events"]
    save_config(c)


def test_catalog_has_nullrecords_voices():
    # The base options come from the NullRecords audiobook catalog.
    assert "narrator" in VOICE_CATALOG
    assert VOICE_CATALOG["bob"].name == "Bob the Humanist"
    assert VOICE_CATALOG["narrator"].riva_id == "English-US.Male-1"
    assert catalog.get_voice("nonexistent").key == "narrator"  # safe default


def test_speaker_disabled_returns_not_ok():
    _voice(enabled=False)
    r = spk.get_speaker().speak("hi")
    assert r.ok is False and r.provider == "none"


def test_speaker_none_provider_muted():
    _voice(enabled=True, provider="none")
    assert spk.get_speaker().speak("hi").ok is False


def test_quiet_hours_blocks(monkeypatch):
    _voice(enabled=True, provider="say", quiet_hours="00:00-23:59")
    r = spk.get_speaker().speak("hi")
    assert r.ok is False and "quiet" in r.detail.lower()


def test_quiet_hours_parsing():
    # Range not crossing midnight.
    assert spk._in_quiet_hours("00:00-23:59") is True
    assert spk._in_quiet_hours("") is False
    assert spk._in_quiet_hours("garbage") is False


def test_pyttsx3_falls_back_to_say(monkeypatch):
    """provider=pyttsx3 with pyttsx3 absent but `say` present → uses say."""
    _voice(enabled=True, provider="pyttsx3")
    # Simulate pyttsx3 missing.
    monkeypatch.setattr(spk.Speaker, "_speak_pyttsx3",
                        lambda self, *a: spk.SpeakResult(ok=False, provider="pyttsx3",
                                                         detail="pyttsx3 not installed."))
    monkeypatch.setattr(spk.shutil, "which", lambda n: "/usr/bin/say" if n == "say" else None)
    called = {}

    def fake_say(self, *a):
        called["say"] = True
        return spk.SpeakResult(ok=True, provider="say")

    monkeypatch.setattr(spk.Speaker, "_speak_say", fake_say)
    r = spk.get_speaker().speak("hello", respect_quiet=False)
    assert r.ok and r.provider == "say" and called.get("say")


# -- notifier -----------------------------------------------------------------

def test_phrase_for_agent_done():
    from buster.events import Event, EventType
    from buster.voice.notifier import phrase_for

    e = Event(type=EventType.RUNTIME_TASK_COMPLETED, title="build the thing")
    assert "finished" in phrase_for(e).lower()
    assert "build the thing" in phrase_for(e)


@pytest.mark.asyncio
async def test_notifier_only_speaks_allowed_events(monkeypatch):
    from buster.events import Event, EventType
    from buster.voice.notifier import VoiceNotifier

    _voice(enabled=True, provider="say", announce_events=["runtime.task.completed"])

    spoke = []
    monkeypatch.setattr(spk.Speaker, "available", lambda self: True)
    monkeypatch.setattr(spk.Speaker, "speak",
                        lambda self, text, **k: spoke.append(text) or spk.SpeakResult(ok=True))

    n = VoiceNotifier()
    # An allowed event → speaks.
    await n._handle(Event(type=EventType.RUNTIME_TASK_COMPLETED, title="X"))
    # A non-allowed event → silent.
    await n._handle(Event(type=EventType.TOOL_STARTED, title="Y"))
    assert len(spoke) == 1 and "X" in spoke[0]


@pytest.mark.asyncio
async def test_notifier_ignores_its_own_announce(monkeypatch):
    from buster.events import Event, EventType
    from buster.voice.notifier import VoiceNotifier

    _voice(enabled=True, provider="say", announce_events=["voice.announce"])
    monkeypatch.setattr(spk.Speaker, "available", lambda self: True)
    called = []
    monkeypatch.setattr(spk.Speaker, "speak",
                        lambda self, *a, **k: called.append(1) or spk.SpeakResult(ok=True))
    n = VoiceNotifier()
    await n._handle(Event(type=EventType.VOICE_ANNOUNCE, title="loop?"))
    assert not called  # never announces its own announcements


# -- neural (Riva/PersonaPlex) ------------------------------------------------

@pytest.mark.asyncio
async def test_neural_synthesize_none_without_websockets(monkeypatch):
    """If websockets import fails, synthesize returns None (caller falls back)."""
    import builtins

    from buster.voice import neural

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "websockets":
            raise ImportError("no websockets")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    assert await neural.synthesize("hi", "wss://localhost:8443") is None


def test_neural_wrap_wav_pcm_and_riff(tmp_path):
    from buster.voice import neural

    # Raw PCM gets a WAV header.
    pcm = b"\x00\x01" * 100
    p = neural._wrap_wav(pcm, 24000)
    assert p.endswith(".wav")
    import wave

    with wave.open(p, "rb") as w:
        assert w.getframerate() == 24000 and w.getnchannels() == 1
    # Already-RIFF audio is kept as-is.
    riff = b"RIFF" + b"\x00" * 40
    p2 = neural._wrap_wav(riff, 24000)
    from pathlib import Path

    assert Path(p2).read_bytes()[:4] == b"RIFF"


@pytest.mark.asyncio
async def test_riva_provider_falls_back_when_server_down(monkeypatch):
    _voice(enabled=True, provider="riva")
    c = load_config()
    c.voice.riva_url = "wss://localhost:19999"  # nothing there
    save_config(c)

    from buster.voice import neural

    async def no_audio(*a, **k):
        return neural.NeuralTTSResult(ok=False, detail="unreachable")

    monkeypatch.setattr(neural, "synthesize_and_play", no_audio)
    # Force pyttsx3 absent + say present so the fallback path is deterministic.
    monkeypatch.setattr(spk.Speaker, "_speak_pyttsx3",
                        lambda self, *a: spk.SpeakResult(ok=False, provider="pyttsx3",
                                                         detail="not installed"))
    monkeypatch.setattr(spk.shutil, "which", lambda n: "/usr/bin/say" if n == "say" else None)
    monkeypatch.setattr(spk.Speaker, "_speak_say",
                        lambda self, *a: spk.SpeakResult(ok=True, provider="say"))
    r = spk.get_speaker().speak("neural test", respect_quiet=False)
    assert r.ok and r.provider == "say" and "neural unavailable" in r.detail
