"""Synthesizer over piper-tts 1.8.0. The only module importing piper."""

from __future__ import annotations

from typing import Self

from jarvis.audio import PcmClip
from jarvis.core.vocabulary import VoiceId
from jarvis.settings import ModelSettings


class PiperSynthesizer:
    """One ``PiperVoice.load(model_path)`` per configured voice, loaded at boot.
    ``synthesize`` runs ``voice.synthesize(text)`` on a worker thread and concatenates the
    ``AudioChunk.audio_int16_array``s into one ``PcmClip`` at the voice's native rate."""

    @classmethod
    async def load(cls, settings: ModelSettings) -> Self:
        raise NotImplementedError

    async def synthesize(self, text: str, voice: VoiceId) -> PcmClip:
        raise NotImplementedError
