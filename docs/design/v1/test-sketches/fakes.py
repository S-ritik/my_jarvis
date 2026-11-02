"""Scripted fakes and scenario helpers shared by both seam suites (tests/support in the real repo).

Determinism strategy
--------------------
Seam-1 tests run on a **virtual-time event loop** (e.g. the ``looptime`` pytest plugin, or a
40-line custom loop): ``asyncio.sleep`` and ``loop.time()`` are virtual and time only
advances when every task is blocked. Fakes therefore model *real* timing -- the mic
delivers a frame every 80 ms, the player finishes a clip after its duration, a brain
step takes 50 ms -- and every consequence of frame *k* is fully processed before frame
*k+1* arrives. No sleeps, no polling, no test hooks in the core.

Listening policy still counts samples (the fake mic's frames), and cue randomness comes
from ``Random(seed)``. Fakes exist only at hardware/process edges; Listener, Router,
SafetyGate, Chunker, CueBoard and the Memory Store (temp SQLite) are the real ones.

Frames are *tagged*: sample[0] = wake score x 10_000, sample[1] = VAD probability x 10_000,
sample[2] = word id. Tagged scorers and the transcriber decode them, so a scenario reads
"1 s silence, wake at 0.8 for 2 frames, 1.2 s of 'clear the logs', 0.5 s silence".
"""

from __future__ import annotations

import asyncio
import dataclasses
from collections import deque
from collections.abc import AsyncIterator, Iterable, Sequence
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from random import Random
from typing import TypeVar

import numpy as np

from jarvis.audio import FRAME_SAMPLES, AudioFrame, Pcm, PcmClip
from jarvis.brain.port import (
    Allow,
    Availability,
    Available,
    BackendCapabilities,
    BackendKind,
    BrainError,
    BrainErrorKind,
    BrainEvent,
    BrainFailed,
    BrainSession,
    JsonObject,
    JsonValue,
    SessionSpec,
    TextDelta,
    ToolAction,
    ToolCall,
    ToolFinished,
    TurnEnded,
    Unavailable,
    UseCustomTool,
)
from jarvis.control.server import ControlServer, InstanceLock
from jarvis.core.assistant import AssistantCore
from jarvis.core.bus import EventSubscription
from jarvis.core.ports import (
    AuditEntry,
    ItemFinished,
    ItemStarted,
    PlaybackEnd,
    PlayerEvent,
    Ports,
)
from jarvis.core.vocabulary import (
    ActionDone,
    ActionResult,
    AppDirectory,
    CuePlayed,
    CueEvent,
    DesktopIntent,
    DomainEvent,
    Level,
    LineRendition,
    SentenceSpoken,
    TurnFinished,
    TurnOutcome,
    TurnStarted,
    VoiceId,
)
from jarvis.memory.store import MemoryStore
from jarvis.memory.tools import MemoryContext
from jarvis.settings import Settings, XdgPaths, default_settings

E = TypeVar("E")
FRAME_S = FRAME_SAMPLES / 16_000

# --------------------------------------------------------------------------- tagged audio


class AudioScript:
    """Builds tagged frames and decodes them back to words for the fake transcriber."""

    def __init__(self) -> None:
        self._words: list[str] = [""]

    def _frame(self, wake: float = 0.0, vad: float = 0.0, word: str = "") -> AudioFrame:
        frame = np.zeros(FRAME_SAMPLES, dtype=np.int16)
        frame[0], frame[1], frame[2] = round(wake * 10_000), round(vad * 10_000), self._word_id(word)
        return frame

    def _word_id(self, word: str) -> int:
        if word not in self._words:
            self._words.append(word)
        return self._words.index(word)

    def silence(self, seconds: float) -> list[AudioFrame]:
        return [self._frame() for _ in range(round(seconds / FRAME_S))]

    def wake(self, score: float, frames: int = 2) -> list[AudioFrame]:
        """Frames scoring ``score`` that carry the words "hey jarvis" (so pre-roll is visible)."""
        return [self._frame(wake=score, vad=0.9, word="hey" if i == 0 else "jarvis") for i in range(frames)]

    def speech(self, text: str, seconds: float) -> list[AudioFrame]:
        words = text.split()
        n = max(len(words), round(seconds / FRAME_S))
        return [self._frame(vad=0.9, word=words[i * len(words) // n]) for i in range(n)]

    def murmur(self, seconds: float, vad: float = 0.4) -> list[AudioFrame]:
        """Between onset and silence thresholds: neither voiced nor silent."""
        return [self._frame(vad=vad) for _ in range(round(seconds / FRAME_S))]

    def words_in(self, audio: Pcm) -> str:
        ids = [int(audio[i + 2]) for i in range(0, len(audio), FRAME_SAMPLES)]
        out: list[str] = []
        for wid in ids:
            if wid and (not out or out[-1] != self._words[wid]):
                out.append(self._words[wid])
        return " ".join(out)


class ScriptedMic:
    """Delivers fed frames every 80 ms (virtual), then room silence. Records open/close."""

    def __init__(self, script: AudioScript) -> None:
        self._script = script
        self._pending: deque[AudioFrame] = deque()
        self.is_open = False
        self.opened = 0

    def feed(self, *segments: Iterable[AudioFrame]) -> None:
        for seg in segments:
            self._pending.extend(seg)

    @property
    def pending(self) -> int:
        return len(self._pending)

    def open(self) -> AbstractAsyncContextManager[AsyncIterator[AudioFrame]]:
        @asynccontextmanager
        async def stream() -> AsyncIterator[AsyncIterator[AudioFrame]]:
            self.is_open, self.opened = True, self.opened + 1
            try:
                yield self._frames()
            finally:
                self.is_open = False

        return stream()

    async def _frames(self) -> AsyncIterator[AudioFrame]:
        while True:
            await asyncio.sleep(FRAME_S)
            yield self._pending.popleft() if self._pending else self._script.silence(FRAME_S)[0]


class TaggedWake:
    async def score(self, frame: AudioFrame) -> float:
        return int(frame[0]) / 10_000

    def reset(self) -> None:
        pass


class TaggedVad:
    async def speech_probability(self, frame: AudioFrame) -> float:
        return int(frame[1]) / 10_000

    def reset(self) -> None:
        pass


@dataclass
class TaggedTranscriber:
    script: AudioScript
    received: list[str] = field(default_factory=list)

    async def transcribe(self, utterance: Pcm) -> str:
        await asyncio.sleep(0.3)
        text = self.script.words_in(utterance)
        self.received.append(text)
        return text


# --------------------------------------------------------------------------- scripted brain


@dataclass(frozen=True)
class Say:
    text: str


@dataclass(frozen=True)
class Tool:
    action: ToolAction
    succeeds: bool = True
    args: JsonObject = field(default_factory=dict)
    """For ``UseCustomTool``: the arguments the session passes to the ``BrainTool`` handler."""


@dataclass(frozen=True)
class Fail:
    kind: BrainErrorKind


@dataclass(frozen=True)
class Hang:
    """Stream nothing until interrupted (or forever, for the drain path / timeouts)."""


Step = Say | Tool | Fail | Hang


def say(text: str) -> Say:
    return Say(text)


def tool(action: ToolAction, succeeds: bool = True, **args: JsonValue) -> Tool:
    return Tool(action, succeeds, dict(args))


class ScriptedBrain:
    """A ``BrainBackend``. Each ``send`` consumes the next scripted turn.

    After a ``Deny`` it *keeps going* (like a backend that ignores the hint), so the core's
    discard rule is what keeps the remainder silent.
    """

    def __init__(self, turns: list[list[Step]], *, kind: BackendKind = BackendKind.CLAUDE_CODE,
                 availability: Availability = Available(), interruptible: bool = True,
                 caps: BackendCapabilities = BackendCapabilities(gates_tools=True, custom_tools=True)) -> None:
        self._turns = deque(turns)
        self._kind = kind
        self.availability = availability
        self.interruptible = interruptible
        self.caps = caps
        self.specs: list[SessionSpec] = []
        self.sent: list[tuple[int, str]] = []
        self.verdicts: list[tuple[ToolCall, object]] = []
        self.interrupts = 0

    @property
    def kind(self) -> BackendKind:
        return self._kind

    @property
    def capabilities(self) -> BackendCapabilities:
        return self.caps

    async def probe(self) -> Availability:
        return self.availability

    async def open(self, spec: SessionSpec) -> BrainSession | BrainError:
        if isinstance(self.availability, Unavailable):
            return BrainError(BrainErrorKind.UNAVAILABLE, self.availability.reason, None)
        self.specs.append(spec)
        return _ScriptedSession(self, spec, session_no=len(self.specs))


class _ScriptedSession:
    def __init__(self, brain: ScriptedBrain, spec: SessionSpec, session_no: int) -> None:
        self._brain, self._spec, self._no = brain, spec, session_no
        self._interrupted = asyncio.Event()

    @property
    def interruptible(self) -> bool:
        return self._brain.interruptible

    async def send(self, text: str) -> AsyncIterator[BrainEvent]:
        self._brain.sent.append((self._no, text))
        self._interrupted.clear()
        for i, step in enumerate(self._brain._turns.popleft() if self._brain._turns else []):
            await asyncio.sleep(0.05)
            if self._interrupted.is_set():
                yield TurnEnded(interrupted=True)
                return
            match step:
                case Say(text=t):
                    yield TextDelta(t)
                case Tool(action=a, succeeds=ok, args=args):
                    call = ToolCall(f"call-{i}", type(a).__name__, a, args)
                    verdict = await self._spec.gate(call)
                    self._brain.verdicts.append((call, verdict))
                    if isinstance(verdict, Allow):
                        if isinstance(a, UseCustomTool):  # the backend runs JARVIS's in-process tool
                            handler = next(t.handler for t in self._spec.tools if t.name == a.name)
                            ok = not (await handler(args)).failed
                        yield ToolFinished(call.call_id, ok)
                case Fail(kind=k):
                    yield BrainFailed(BrainError(k, "scripted", None))
                    return
                case Hang():
                    await self._interrupted.wait()
                    yield TurnEnded(interrupted=True)
                    return
        yield TurnEnded(interrupted=False)

    async def interrupt(self) -> None:
        self._brain.interrupts += 1
        self._interrupted.set()

    async def close(self) -> None:
        pass


def unavailable_backend(kind: BackendKind, reason: str) -> ScriptedBrain:
    return ScriptedBrain([], kind=kind, availability=Unavailable(reason, fix="install it"))


# --------------------------------------------------------------------------- voice, desktop, audit, clock


@dataclass
class EchoSynth:
    """0.25 s of audio per word at 22.05 kHz; takes 50 ms (virtual) to 'render'."""

    rendered: list[tuple[VoiceId, str]] = field(default_factory=list)

    async def synthesize(self, text: str, voice: VoiceId) -> PcmClip:
        await asyncio.sleep(0.05)
        self.rendered.append((voice, text))
        frames = int(22_050 * 0.25 * max(1, len(text.split())))
        return PcmClip(np.zeros((frames, 1), dtype=np.int16), 22_050, 1)


class TimedPlayer:
    """Plays items back to back in virtual time; ``flush`` finishes everything as FLUSHED."""

    def __init__(self) -> None:
        self._events: asyncio.Queue[PlayerEvent] = asyncio.Queue()
        self._queue: deque[tuple[int, PcmClip]] = deque()
        self._task: asyncio.Task[None] | None = None
        self.played: list[int] = []

    def enqueue(self, item_id: int, clip: PcmClip) -> None:
        self._queue.append((item_id, clip))
        if self._task is None or self._task.done():
            self._task = asyncio.get_running_loop().create_task(self._play())

    async def _play(self) -> None:
        while self._queue:
            item_id, clip = self._queue[0]
            self._events.put_nowait(ItemStarted(item_id))
            await asyncio.sleep(clip.duration_s)
            self._queue.popleft()
            self.played.append(item_id)
            self._events.put_nowait(ItemFinished(item_id, PlaybackEnd.COMPLETED))

    def flush(self) -> None:
        if self._task:
            self._task.cancel()
        while self._queue:
            self._events.put_nowait(ItemFinished(self._queue.popleft()[0], PlaybackEnd.FLUSHED))

    async def events(self) -> AsyncIterator[PlayerEvent]:
        while True:
            yield await self._events.get()


@dataclass
class FakeClips:
    available: frozenset[str]

    async def load(self, clip: str) -> PcmClip | None:
        if clip not in self.available:
            return None
        return PcmClip(np.zeros((int(44_100 * 0.6), 2), dtype=np.int16), 44_100, 2)


@dataclass
class FakeDesktop:
    apps: AppDirectory
    results: dict[type, ActionResult] = field(default_factory=dict)
    performed: list[DesktopIntent] = field(default_factory=list)

    async def perform(self, intent: DesktopIntent) -> ActionResult:
        self.performed.append(intent)
        return self.results.get(type(intent), ActionDone())

    async def app_directory(self) -> AppDirectory:
        return self.apps


@dataclass
class RecordingAudit:
    entries: list[AuditEntry] = field(default_factory=list)

    async def record(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


class LoopClock:
    """Brain-side time = the (virtual) loop clock; wall time fixed at 2026-11-02 15:42 local."""

    def monotonic(self) -> float:
        return asyncio.get_running_loop().time()

    def now(self) -> datetime:
        return datetime.fromisoformat("2026-11-02T15:42:00+01:00")

    async def sleep(self, seconds: float) -> None:
        await asyncio.sleep(seconds)


# --------------------------------------------------------------------------- event log


class TurnView:
    def __init__(self, events: Sequence[DomainEvent]) -> None:
        self.events: list[DomainEvent] = [e for e in events if not isinstance(e, Level)]

    @property
    def outcome(self) -> TurnOutcome:
        return self.first(TurnFinished).outcome

    def all(self, kind: type[E]) -> list[E]:
        return [e for e in self.events if isinstance(e, kind)]

    def first(self, kind: type[E]) -> E:
        return self.all(kind)[0]

    def after(self, kind: type[object]) -> TurnView:
        i = next(i for i, e in enumerate(self.events) if isinstance(e, kind))
        return TurnView(self.events[i + 1:])

    def cues(self) -> list[CueEvent]:
        return [e.cue for e in self.all(CuePlayed)]

    def spoken(self) -> list[str]:
        """Everything synthesized aloud, in order: sentences and cue fallback lines."""
        out: list[str] = []
        for e in self.events:
            if isinstance(e, SentenceSpoken):
                out.append(e.text)
            elif isinstance(e, CuePlayed) and isinstance(e.rendition, LineRendition):
                out.append(e.rendition.text)
        return out


class EventLog:
    def __init__(self, subscription: EventSubscription) -> None:
        self._it = aiter(subscription)
        self.seen: list[DomainEvent] = []

    async def next(self, kind: type[E], *, within_s: float = 30.0) -> E:
        async with asyncio.timeout(within_s):  # virtual seconds
            async for env in self._it:
                self.seen.append(env.event)
                if isinstance(env.event, kind):
                    return env.event
        raise AssertionError(f"stream ended before {kind.__name__}")

    async def turn(self, *, within_s: float = 30.0) -> TurnView:
        """Events from the next ``TurnStarted`` through its ``TurnFinished``."""
        await self.next(TurnStarted, within_s=within_s)
        start = len(self.seen) - 1
        await self.next(TurnFinished, within_s=within_s)
        return TurnView(self.seen[start:])

    async def quiet(self, seconds: float) -> TurnView:
        """Everything emitted during the next ``seconds`` of virtual time."""
        start = len(self.seen)
        try:
            async with asyncio.timeout(seconds):
                async for env in self._it:
                    self.seen.append(env.event)
        except TimeoutError:
            pass
        return TurnView(self.seen[start:])


# --------------------------------------------------------------------------- harnesses


@dataclass
class CoreHarness:
    core: AssistantCore
    settings: Settings
    audio: AudioScript
    mic: ScriptedMic
    log: EventLog
    brain: ScriptedBrain
    oracle: ScriptedBrain
    transcriber: TaggedTranscriber
    synth: EchoSynth
    player: TimedPlayer
    desktop: FakeDesktop
    audit: RecordingAudit
    store: MemoryStore


def make_settings(tmp: Path, **changes: object) -> Settings:
    xdg = XdgPaths(tmp / "config", tmp / "data", tmp / "state", Path(tmp / "run"))
    base = default_settings(xdg=xdg, home=Path("/home/me"))
    return dataclasses.replace(base, **changes)  # type: ignore[arg-type]


COMMITTED_CLIPS = frozenset({"mech/defensive_systems_online", *(f"acolyte/AcolyteWhat{i}" for i in range(1, 6)),
                             *(f"acolyte/AcolyteYes{i}" for i in range(1, 5)), "cues/jobs_done", "cues/work_complete"})


@asynccontextmanager
async def core_harness(tmp: Path, *, brain: ScriptedBrain | None = None, oracle: ScriptedBrain | None = None,
                       desktop: FakeDesktop | None = None, settings: Settings | None = None,
                       seed: int = 7) -> AsyncIterator[CoreHarness]:
    settings = settings or make_settings(tmp)
    audio = AudioScript()
    clock = LoopClock()
    brain = brain or ScriptedBrain([])
    oracle = oracle or unavailable_backend(BackendKind.ANTIGRAVITY, "Antigravity is not installed.")
    store = await MemoryStore.open(tmp / "memory.db", now=clock.now)
    h_desktop = desktop or FakeDesktop(AppDirectory(aliases={}, installed={}))
    mic, transcriber, synth, player, audit = ScriptedMic(audio), TaggedTranscriber(audio), EchoSynth(), TimedPlayer(), RecordingAudit()
    ports = Ports(
        microphone=mic, wake=TaggedWake(), vad=TaggedVad(), transcriber=transcriber,
        brains={BackendKind.CLAUDE_CODE: brain, BackendKind.ANTIGRAVITY: oracle},
        synthesizer=synth, player=player, clips=FakeClips(COMMITTED_CLIPS), desktop=h_desktop,
        context=MemoryContext(store, settings.memory), audit=audit, clock=clock, rng=Random(seed),
    )
    core = AssistantCore(ports, settings)
    log = EventLog(core.subscribe(capacity=None))  # before boot: sees the boot sequence
    async with core:
        yield CoreHarness(core, settings, audio, mic, log, brain, oracle, transcriber, synth, player,
                          h_desktop, audit, store)


@dataclass
class SocketHarness:
    core: CoreHarness
    socket_path: Path
    lock: InstanceLock


@asynccontextmanager
async def socket_harness(tmp: Path, *, brain: ScriptedBrain | None = None) -> AsyncIterator[SocketHarness]:
    """Real server on a temp runtime dir (kept short: AF_UNIX paths are limited to 107 bytes)."""
    async with core_harness(tmp, brain=brain) as h:
        with InstanceLock.acquire(h.settings.paths.runtime_dir) as lock:
            async with ControlServer.serving(h.core, lock, h.settings.control) as server:
                yield SocketHarness(h, server.socket_path, lock)
