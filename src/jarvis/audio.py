"""Audio value types shared by the core and the audio adapters.

This is the only non-adapter module that names numpy. Everything else refers to
``AudioFrame`` / ``Pcm`` / ``PcmClip`` and calls the helpers below, so the core never
assumes a dtype, a shape or a library.

Listening-side time in JARVIS is *sample time*: every duration in the listening
policies is converted once, here, from milliseconds to a sample count at 16 kHz.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final, TypeAlias

import numpy as np
import numpy.typing as npt

SAMPLE_RATE: Final = 16_000
"""Capture rate (ADR 02). The microphone adapter opens the device at this rate; no resampling in Python."""

FRAME_SAMPLES: Final = 1_280
"""One capture block: 80 ms of mono int16 audio (ADR 02, OpenWakeWord's native chunk)."""

AudioFrame: TypeAlias = npt.NDArray[np.int16]
"""One capture block: shape ``(FRAME_SAMPLES,)``, mono, 16 kHz, int16. Never written to disk."""

Pcm: TypeAlias = npt.NDArray[np.int16]
"""A captured utterance: concatenated frames, mono, 16 kHz, int16. Lives in memory only."""


@dataclass(frozen=True, eq=False)
class PcmClip:
    """Something the Player can play: synthesized speech or a decoded cue clip.

    Carries its own rate and channel count; the Player reopens its stream when these
    change between items (ADR 02: PipeWire resamples, Python never does).
    """

    samples: npt.NDArray[np.int16]
    """Shape ``(frames, channels)``."""
    sample_rate: int
    channels: int

    @property
    def duration_s(self) -> float:
        return len(self.samples) / self.sample_rate


def ms_to_samples(ms: int) -> int:
    """Convert a policy duration to capture samples (16 kHz)."""
    return ms * SAMPLE_RATE // 1000


def samples_to_ms(samples: int) -> int:
    return samples * 1000 // SAMPLE_RATE


def concat(frames: Sequence[AudioFrame]) -> Pcm:
    """Join capture frames into one utterance buffer (pre-roll + capture)."""
    raise NotImplementedError  # np.concatenate(frames) if frames else np.zeros(0, np.int16)


def rms(frame: AudioFrame) -> float:
    """Normalized RMS level in [0, 1] for the HUD's Listening ring."""
    raise NotImplementedError  # sqrt(mean((frame / 32768.0) ** 2))
