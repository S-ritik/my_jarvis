"""Every port the Assistant Core depends on, and the ``Ports`` bundle that wires them.

Rules every adapter obeys (so the core needs no vendor knowledge and no ``except VendorError``):

* All I/O ports are ``async``. Blocking/CPU work (ONNX scoring, Whisper, Piper, sqlite)
  runs on a worker thread *inside* the adapter (``asyncio.to_thread`` / an executor).
* Ports carry **no policy**: no thresholds, debounce, endpointing, routing, phrasing.
  The wake scorer returns a raw score; the core decides what a detection is.
* Expected failures are values (``ActionFailed``, ``BrainFailed``, ``None`` clip).
  An unexpected exception escaping a port is a bug; the core contains it per turn,
  reports ``ErrorOccurred(INTERNAL)`` out loud and carries on.
* Per-frame ports (``WakeScorer``, ``VadScorer``) must answer within one frame period
  (80 ms); the core awaits them in-line. Everything slower is run as a turn task.

The Brain backend port lives in ``jarvis.brain.port``; the core sees it through
``Ports.brains``. Memory reaches the core only as a ``BrainContext``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from random import Random
from typing import Protocol, TypeAlias

from jarvis.audio import AudioFrame, Pcm, PcmClip
from jarvis.brain.port import BackendKind, BrainBackend, BrainTool, ToolCall, DenyCategory
from jarvis.core.vocabulary import ActionResult, AppDirectory, DesktopIntent, TurnId, VoiceId

# --------------------------------------------------------------------------- Ears


class Microphone(Protocol):
    def open(self) -> AbstractAsyncContextManager[AsyncIterator[AudioFrame]]:
        """Open the capture stream; iterate frames (16 kHz mono int16, 1280 samples) until exit.

        Exiting the context closes the device (Asleep = mic closed, ADR privacy story).
        The adapter's PortAudio callback only copies the block and hands it to the loop
        (``loop.call_soon_threadsafe``); it never blocks and never drops silently: if the
        loop falls behind it logs an overrun.
        """
        ...


class WakeScorer(Protocol):
    async def score(self, frame: AudioFrame) -> float:
        """Raw wake-word score in [0, 1] for this frame. No threshold, no patience."""
        ...

    def reset(self) -> None:
        """Clear internal feature buffers (called on detection and on leaving Idle)."""
        ...


class VadScorer(Protocol):
    async def speech_probability(self, frame: AudioFrame) -> float:
        """Speech probability for this capture frame.

        The adapter re-chunks into the VAD's native window with carry-over and returns
        the maximum window probability completed within this frame.
        """
        ...

    def reset(self) -> None:
        """Clear recurrent state and carry-over (called when a capture starts)."""
        ...


class Transcriber(Protocol):
    async def transcribe(self, utterance: Pcm) -> str:
        """English transcript of an in-memory utterance (may be empty). Never persists audio."""
        ...


# --------------------------------------------------------------------------- Voice


class Synthesizer(Protocol):
    async def synthesize(self, text: str, voice: VoiceId) -> PcmClip:
        """Render one sentence in a Piper voice. Cancellation abandons the result."""
        ...


class PlaybackEnd(StrEnum):
    COMPLETED = "completed"
    FLUSHED = "flushed"
    FAILED = "failed"


@dataclass(frozen=True)
class ItemStarted:
    item_id: int


@dataclass(frozen=True)
class ItemFinished:
    item_id: int
    end: PlaybackEnd


@dataclass(frozen=True)
class OutputLevel:
    rms: float


PlayerEvent: TypeAlias = ItemStarted | ItemFinished | OutputLevel


class Player(Protocol):
    """Single owner of the output device. Plays enqueued clips back to back, in order.

    Reopens its output stream when rate/channels change between items. Publishes output
    RMS at ~30 Hz while playing.
    """

    def enqueue(self, item_id: int, clip: PcmClip) -> None: ...

    def flush(self) -> None:
        """Silence within 100 ms; every queued/playing item finishes as FLUSHED."""
        ...

    def events(self) -> AsyncIterator[PlayerEvent]:
        """Progress events, in order, for the lifetime of the player."""
        ...


class ClipLoader(Protocol):
    async def load(self, clip: str) -> PcmClip | None:
        """Decode a committed clip (WAV or MP3) at its native rate/channels. None if missing or undecodable."""
        ...


# --------------------------------------------------------------------------- desktop, memory, audit, time


class DesktopActions(Protocol):
    """Every bypass side effect (wpctl, playerctl, systemd-run --user). No phrasing, no policy."""

    async def perform(self, intent: DesktopIntent) -> ActionResult: ...

    async def app_directory(self) -> AppDirectory:
        """Configured aliases + installed desktop entries, as an immutable snapshot."""
        ...


class BrainContext(Protocol):
    """What every new Brain Session receives besides its persona: a system-prompt preamble
    and extra tools. Implemented by ``jarvis.memory.tools.MemoryContext``.

    The core never reads or writes memory itself; it only hands these to new sessions.
    """

    async def preamble(self) -> str: ...

    def tools(self) -> tuple[BrainTool, ...]: ...


@dataclass(frozen=True)
class AuditEntry:
    at: datetime
    turn: TurnId
    persona: str
    category: DenyCategory
    call: ToolCall


class AuditLog(Protocol):
    async def record(self, entry: AuditEntry) -> None:
        """Append one refused request (JSON line) to the safety audit log."""
        ...


class Clock(Protocol):
    """Wall/monotonic time for the *brain side* (timeouts, latency log, time-of-day answers).

    Listening-side time never comes from here: it is counted in audio samples.
    """

    def monotonic(self) -> float: ...

    def now(self) -> datetime:
        """Local, timezone-aware wall time (for "what time is it" and audit timestamps)."""
        ...

    async def sleep(self, seconds: float) -> None:
        """Deadline primitive. A test clock resolves these only when advanced."""
        ...


# --------------------------------------------------------------------------- the bundle


@dataclass(frozen=True)
class Ports:
    microphone: Microphone
    wake: WakeScorer
    vad: VadScorer
    transcriber: Transcriber
    brains: Mapping[BackendKind, BrainBackend]
    """The Brain Session factory: one backend per kind; personas pick by ``Persona.backend``."""
    synthesizer: Synthesizer
    player: Player
    clips: ClipLoader
    desktop: DesktopActions
    context: BrainContext
    audit: AuditLog
    clock: Clock
    rng: Random
    """Cue selection randomness; tests pass ``Random(seed)``."""
