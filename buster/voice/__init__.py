"""Voice: text-to-speech talk-back + the voice catalog.

Voices are based on the NullRecords audiobook pipeline's VoiceConfig catalog
(Narrator, Bob the Humanist, young/old male/female). pyttsx3 is the default
provider (offline, no GPU, cross-platform); a Riva/PersonaPlex neural server is
used when configured/reachable; macOS 'say' is available too.
"""

from buster.voice.catalog import VOICE_CATALOG, VoiceOption
from buster.voice.speaker import get_speaker, speak

__all__ = ["VOICE_CATALOG", "VoiceOption", "get_speaker", "speak"]
