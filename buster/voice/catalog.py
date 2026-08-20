"""Voice catalog — based on the NullRecords audiobook pipeline VoiceConfig set.

Each option maps a friendly key to per-provider voice identifiers:
  * riva_id      — NVIDIA Riva / PersonaPlex voice id (e.g. "English-US.Male-1")
  * pyttsx3_hint — substring matched against installed pyttsx3 system voices
  * say_voice    — macOS `say` voice name
  * web_hint     — substring matched against browser SpeechSynthesis voices

Thanks to the NullRecords press project for the original voice design.
"""

from __future__ import annotations

from pydantic import BaseModel


class VoiceOption(BaseModel):
    key: str
    name: str
    tone: str = "neutral"
    description: str = ""
    riva_id: str = ""
    pyttsx3_hint: str = ""
    say_voice: str = ""
    web_hint: str = ""


VOICE_CATALOG: dict[str, VoiceOption] = {
    "narrator": VoiceOption(
        key="narrator", name="Narrator", tone="dramatic",
        description="Deep, dramatic narrator voice",
        riva_id="English-US.Male-1", pyttsx3_hint="daniel",
        say_voice="Daniel", web_hint="Daniel"),
    "narrator_female": VoiceOption(
        key="narrator_female", name="Narrator (Female)", tone="dramatic",
        description="Warm, expressive female narrator",
        riva_id="English-US.Female-1", pyttsx3_hint="samantha",
        say_voice="Samantha", web_hint="Samantha"),
    "bob": VoiceOption(
        key="bob", name="Bob the Humanist", tone="friendly",
        description="Friendly, knowledgeable voice for annotations",
        riva_id="English-US.Male-2", pyttsx3_hint="alex",
        say_voice="Alex", web_hint="Alex"),
    "male_young": VoiceOption(
        key="male_young", name="Young Male", tone="neutral",
        description="Youthful male voice",
        riva_id="English-US.Male-1", pyttsx3_hint="fred",
        say_voice="Fred", web_hint="Fred"),
    "male_old": VoiceOption(
        key="male_old", name="Older Male", tone="stern",
        description="Older, measured male voice",
        riva_id="English-US.Male-2", pyttsx3_hint="ralph",
        say_voice="Ralph", web_hint="Ralph"),
    "female_young": VoiceOption(
        key="female_young", name="Young Female", tone="gentle",
        description="Youthful female voice",
        riva_id="English-US.Female-1", pyttsx3_hint="victoria",
        say_voice="Victoria", web_hint="Victoria"),
    "female_older": VoiceOption(
        key="female_older", name="Older Female", tone="gentle",
        description="Older, measured female voice",
        riva_id="English-US.Female-2", pyttsx3_hint="karen",
        say_voice="Karen", web_hint="Karen"),
}


def get_voice(key: str) -> VoiceOption:
    return VOICE_CATALOG.get(key, VOICE_CATALOG["narrator"])
