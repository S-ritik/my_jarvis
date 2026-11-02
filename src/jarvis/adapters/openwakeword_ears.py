"""Wake Scorer and VAD Scorer over openwakeword 0.6.0 (ONNX). The only module importing openwakeword.

``OMP_NUM_THREADS=1`` is set by ``jarvis.cli`` before this module is imported (ADR 03).
No policy here: ``predict`` is called without ``patience``/``threshold``/``debounce_time``.
"""

from __future__ import annotations

from typing import Self

from jarvis.audio import AudioFrame
from jarvis.settings import ModelSettings


class OpenWakeWordScorer:
    """``openwakeword.Model(wakeword_models=[path], vad_threshold=settings.wake_vad_threshold,
    inference_framework="onnx")``; ``score`` = ``predict(frame)["hey_jarvis..."]`` on a worker thread."""

    @classmethod
    async def load(cls, settings: ModelSettings) -> Self:
        raise NotImplementedError

    async def score(self, frame: AudioFrame) -> float:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError  # model.reset()


class SileroVadScorer:
    """Silero via ``openwakeword.vad.VAD`` (ONNX, no torch). Re-chunks each 1280-sample frame
    into native windows with carry-over; returns the max window probability in the frame."""

    @classmethod
    async def load(cls, settings: ModelSettings) -> Self:
        raise NotImplementedError

    async def speech_probability(self, frame: AudioFrame) -> float:
        raise NotImplementedError

    def reset(self) -> None:
        raise NotImplementedError  # vad.reset_states(); carry = empty
