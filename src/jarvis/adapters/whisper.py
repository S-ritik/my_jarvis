"""Transcriber over faster-whisper 1.2.1. The only module importing faster_whisper."""

from __future__ import annotations

from typing import Self

from jarvis.audio import Pcm
from jarvis.settings import ModelSettings


class WhisperTranscriber:
    """``WhisperModel(settings.whisper_model, device="cpu", compute_type="int8",
    cpu_threads=settings.whisper_cpu_threads, local_files_only=True, download_root=models_dir)``.
    ``transcribe`` converts int16 -> float32/32768, runs ``model.transcribe(audio, language="en",
    beam_size=settings.whisper_beam_size, vad_filter=False)`` on a worker thread and joins segments."""

    @classmethod
    async def load(cls, settings: ModelSettings) -> Self:
        raise NotImplementedError

    async def transcribe(self, utterance: Pcm) -> str:
        raise NotImplementedError
