"""Speech output: everything between "the assistant wants to say X" and the speaker.

Knowledge owned here: the Sentence Chunker (``. ! ? \\n`` followed by whitespace or end,
>= 4-word guard, end-of-turn flush at any length); speakable normalization (markdown
stripped, fenced/inline code dropped, URLs -> "a link"); synth-ahead pipelining (sentence
n+1 synthesized while n plays, strictly in order, cues interleaved in order); cue
rendering (clip enqueued as-is, or fallback line synthesized); the Player's item ids;
and the single ``flush()`` that silences and forgets everything.

It never emits domain events itself. It *posts* ``SpeechProgress`` values to the core's
inbox; the core's actor turns them into ``SentenceQueued``/``SentenceSpoken``/``CuePlayed``
in the one ordered stream.

Invariant the core relies on: after any call that leaves nothing queued, synthesizing or
playing (including a call that enqueued nothing, e.g. a disabled cue, and ``flush()``),
exactly one ``Drained`` is posted once the pipeline is idle.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeAlias

from jarvis.core.cues import CueBoard
from jarvis.core.ports import Player, Synthesizer
from jarvis.core.vocabulary import CueEvent, CueRendition, TurnId, VoiceId
from jarvis.settings import SpeechSettings

# --------------------------------------------------------------------------- progress posted to the core


@dataclass(frozen=True)
class SentenceReady:
    """A sentence left the chunker and entered the synthesis queue."""

    turn: TurnId | None
    index: int
    text: str
    voice: VoiceId


@dataclass(frozen=True)
class Synthesized:
    turn: TurnId | None
    index: int


@dataclass(frozen=True)
class SentenceStarted:
    turn: TurnId | None
    index: int
    text: str
    voice: VoiceId


@dataclass(frozen=True)
class CueStarted:
    turn: TurnId | None
    cue: CueEvent
    rendition: CueRendition


@dataclass(frozen=True)
class SpeakerLevel:
    rms: float


@dataclass(frozen=True)
class SpeechFailed:
    turn: TurnId | None
    text: str
    detail: str


@dataclass(frozen=True)
class Drained:
    pass


SpeechProgress: TypeAlias = (
    SentenceReady | Synthesized | SentenceStarted | CueStarted | SpeakerLevel | SpeechFailed | Drained
)


# --------------------------------------------------------------------------- pure helpers (private to speech)


class _SentenceChunker:
    """Pure. ``push(delta) -> complete sentences``; ``finish() -> remainder``.

    Kept as a tiny value-holder used only by ``Speech``; the seam tests exercise it via
    Brain text deltas, never directly.
    """

    def __init__(self, min_words: int) -> None:
        raise NotImplementedError

    def push(self, delta: str) -> list[str]:
        raise NotImplementedError
        # buf += delta; out = []
        # scan for terminator in ".!?\n" whose next char exists and is whitespace
        #   ("3.14" never splits: next char is a digit; end-of-buffer is *not* a boundary
        #    until finish(), because more text may follow)
        #   candidate = buf[:i+1]; if word_count(candidate) >= min_words: out.append(candidate); buf = rest
        # return out

    def finish(self) -> str:
        raise NotImplementedError  # rest = buf; buf = ""; return rest


def _speakable(text: str, link_replacement: str) -> str:
    """Strip markdown emphasis/headings/bullets, drop fenced and inline code, replace URLs.
    Code fences can span chunks: ``Speech`` tracks an "inside fence" flag across sentences."""
    raise NotImplementedError


# --------------------------------------------------------------------------- the pipeline


class Speech:
    """Ordered speech/cue output for the core. All methods are called from the core's actor."""

    def __init__(
        self,
        synthesizer: Synthesizer,
        player: Player,
        cues: CueBoard,
        settings: SpeechSettings,
        post: Callable[[SpeechProgress], None],
    ) -> None:
        raise NotImplementedError

    async def run(self) -> None:
        """Background work for the daemon's lifetime: the synthesis worker and the Player
        event pump. Started by ``AssistantCore.__aenter__`` in its task group."""
        raise NotImplementedError
        # slots: deque[Slot]   # Slot = pending sentence (text, voice, future clip) | ready clip | cue line
        # worker: for each pending slot in order: clip = await synthesizer.synthesize(...)  (one at a time,
        #         so n+1 is synthesized while n plays); post(Synthesized); feed_player()
        # feed_player(): while head slot ready: player.enqueue(next_id, clip); remember id -> slot
        # pump: async for ev in player.events():
        #     ItemStarted -> post(SentenceStarted | CueStarted)
        #     ItemFinished(FAILED) -> post(SpeechFailed)
        #     OutputLevel -> post(SpeakerLevel)
        #     when nothing pending/playing -> post(Drained)
        # every slot carries the pipeline generation; flush() bumps it so late results are ignored

    def text(self, turn: TurnId, delta: str, voice: VoiceId) -> None:
        """Brain text delta. Complete sentences are normalized and queued for synthesis."""
        raise NotImplementedError

    def end_of_text(self, turn: TurnId, voice: VoiceId) -> None:
        """The Brain turn ended: flush the chunker remainder (any length)."""
        raise NotImplementedError

    def line(self, turn: TurnId | None, text: str, voice: VoiceId) -> None:
        """A complete line JARVIS composed itself (bypass answer, error, fixed safety line)."""
        raise NotImplementedError

    def cue(self, turn: TurnId | None, cue: CueEvent, voice: VoiceId) -> None:
        """Play a lifecycle cue: a preloaded clip, or the fallback line in ``voice``, or nothing."""
        raise NotImplementedError  # match cues.pick(cue): PlayClip -> ready slot; SpeakLine -> line slot; Silent -> maybe Drained

    def flush(self) -> None:
        """Stop playback now, drop every queued slot, cancel in-flight synthesis, reset the
        chunker and fence state. Then ``Drained`` follows."""
        raise NotImplementedError

    @property
    def busy(self) -> bool:
        raise NotImplementedError
