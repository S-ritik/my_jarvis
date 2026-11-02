"""The Assistant Core's closed domain vocabulary.

Everything the core accepts (``Command``), decides (``Route``, ``DesktopIntent``) and
emits (``DomainEvent``) is a frozen dataclass in a closed union declared here, so every
consumer can ``match`` exhaustively (``assert_never``) and a new variant is flagged by
the type checker at every place that must handle it.

Brain-side vocabulary (tool calls, verdicts, brain errors) lives in ``jarvis.brain.port``
and is re-used here, not duplicated.

Sections: identities -> states -> personas -> commands -> desktop intents -> routes ->
events -> status snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import NewType, TypeAlias

from jarvis.brain.port import Availability, BackendKind, BrainErrorKind, DenyCategory, ToolCall

# --------------------------------------------------------------------------- identities

TurnId = NewType("TurnId", int)
VoiceId = NewType("VoiceId", str)
"""A Piper voice name, e.g. ``en_GB-alan-medium``."""
PersonaName = NewType("PersonaName", str)
"""Canonical lowercase persona key, e.g. ``jarvis``, ``architect``, ``oracle``."""


# --------------------------------------------------------------------------- states


class State(StrEnum):
    """The turn state (HUD rings). Asleep is orthogonal: see ``Status.asleep``."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


class Activation(StrEnum):
    WAKE_WORD = "wake_word"
    PUSH_TO_TALK = "push_to_talk"
    TYPED = "typed"
    """``ask <text>``: the text is the transcript; the Ears are skipped."""


class CueEvent(StrEnum):
    """Tier-1 lifecycle cues (ADR 09)."""

    BOOT = "boot"
    WAKE_ACK = "wake_ack"
    TASK_RECEIVED = "task_received"
    TASK_COMPLETED = "task_completed"
    SAFETY_BLOCKED = "safety_blocked"
    SHUTDOWN = "shutdown"


# --------------------------------------------------------------------------- personas


@dataclass(frozen=True)
class Persona:
    name: PersonaName
    display_name: str
    aliases: tuple[str, ...]
    """Spoken names the Router accepts in "switch to <alias>" (lowercase)."""
    backend: BackendKind
    model: str
    voice: VoiceId
    flavor: str
    """Tier-2 persona flavor paragraph for the system prompt."""


# --------------------------------------------------------------------------- commands (inputs)


@dataclass(frozen=True)
class Talk:
    """Push-to-talk: start Listening now; during Thinking/Speaking this is a barge-in."""


@dataclass(frozen=True)
class Stop:
    """Flush everything and return to Idle."""


@dataclass(frozen=True)
class Sleep:
    """Flush, close the microphone, enter Asleep."""


@dataclass(frozen=True)
class Wake:
    """Leave Asleep: reopen the microphone."""


@dataclass(frozen=True)
class ToggleSleep:
    pass


@dataclass(frozen=True)
class SwitchPersona:
    name: str
    """Persona name or alias, as typed or spoken."""


@dataclass(frozen=True)
class Ask:
    text: str


Command: TypeAlias = Talk | Stop | Sleep | Wake | ToggleSleep | SwitchPersona | Ask


class RejectReason(StrEnum):
    ASLEEP = "asleep"
    """``talk`` while Asleep: the microphone is closed. Send ``wake`` first."""
    UNKNOWN_PERSONA = "unknown_persona"
    PERSONA_UNAVAILABLE = "persona_unavailable"
    EMPTY_REQUEST = "empty_request"
    SHUTTING_DOWN = "shutting_down"


@dataclass(frozen=True)
class Accepted:
    pass


@dataclass(frozen=True)
class Rejected:
    reason: RejectReason
    message: str


CommandResult: TypeAlias = Accepted | Rejected


# --------------------------------------------------------------------------- desktop intents (bypass actions)


class VolumeDirection(StrEnum):
    UP = "up"
    DOWN = "down"


class MediaAction(StrEnum):
    PLAY = "play"
    PAUSE = "pause"
    NEXT = "next"
    PREVIOUS = "previous"


@dataclass(frozen=True)
class AppEntry:
    display_name: str
    desktop_id: str
    """Desktop-entry id (``firefox.desktop``) or a configured command; the adapter launches it."""


@dataclass(frozen=True)
class AppDirectory:
    """Immutable snapshot of launchable apps: configured aliases first, then desktop entries.

    Built by ``DesktopActions.app_directory()`` at boot so the Router stays pure.
    """

    aliases: Mapping[str, AppEntry]
    installed: Mapping[str, AppEntry]

    def find(self, spoken_name: str) -> AppEntry | None:
        raise NotImplementedError  # aliases.get(norm(name)) or installed.get(norm(name))


@dataclass(frozen=True)
class StepVolume:
    direction: VolumeDirection


@dataclass(frozen=True)
class SetVolume:
    percent: int


@dataclass(frozen=True)
class SetMute:
    muted: bool


@dataclass(frozen=True)
class ControlMedia:
    action: MediaAction


@dataclass(frozen=True)
class LaunchApp:
    app: AppEntry


DesktopIntent: TypeAlias = StepVolume | SetVolume | SetMute | ControlMedia | LaunchApp
"""Every bypass side effect. Executed only by the ``DesktopActions`` port (one ``match``)."""


class ActionFailure(StrEnum):
    NO_MEDIA_PLAYER = "no_media_player"
    NO_AUDIO_DEVICE = "no_audio_device"
    LAUNCH_FAILED = "launch_failed"
    TOOL_MISSING = "tool_missing"


@dataclass(frozen=True)
class ActionDone:
    pass


@dataclass(frozen=True)
class ActionFailed:
    failure: ActionFailure
    detail: str
    """For the log; the spoken sentence comes from ``core.phrases``."""


ActionResult: TypeAlias = ActionDone | ActionFailed


# --------------------------------------------------------------------------- routes (Router output)


class DismissReason(StrEnum):
    EMPTY = "empty"
    CANCELLED = "cancelled"


class LocalQuery(StrEnum):
    TIME = "time"
    DATE = "date"


@dataclass(frozen=True)
class Dismiss:
    """End the turn silently ("never mind", empty or wordless transcript)."""

    reason: DismissReason


@dataclass(frozen=True)
class Control:
    """A spoken control command ("switch to Architect", "go to sleep"): same path as the socket."""

    command: SwitchPersona | Sleep


@dataclass(frozen=True)
class Act:
    intent: DesktopIntent


@dataclass(frozen=True)
class Answer:
    query: LocalQuery


@dataclass(frozen=True)
class Think:
    """Not a bypass: send ``text`` to the active persona's Brain."""

    text: str


Route: TypeAlias = Dismiss | Control | Act | Answer | Think


# --------------------------------------------------------------------------- events (the one ordered output stream)


class CaptureEnd(StrEnum):
    ENDPOINT = "endpoint"
    CEILING = "ceiling"


class TurnOutcome(StrEnum):
    ANSWERED = "answered"
    """Brain answered; no acting tool ran."""
    ACTED = "acted"
    """An acting tool ran, or a bypass action succeeded (``task_completed`` played)."""
    ANSWERED_LOCALLY = "answered_locally"
    """Bypass query (time/date) or persona switch confirmation."""
    DISMISSED = "dismissed"
    NO_SPEECH = "no_speech"
    REFUSED = "refused"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class ErrorKind(StrEnum):
    BRAIN_AUTH = "brain_auth"
    BRAIN_USAGE_LIMIT = "brain_usage_limit"
    BRAIN_UNAVAILABLE = "brain_unavailable"
    BRAIN_CRASHED = "brain_crashed"
    BRAIN_TIMEOUT = "brain_timeout"
    PERSONA_UNAVAILABLE = "persona_unavailable"
    ACTION_FAILED = "action_failed"
    TRANSCRIPTION_FAILED = "transcription_failed"
    SPEECH_FAILED = "speech_failed"
    INTERNAL = "internal"

    @staticmethod
    def of_brain(kind: BrainErrorKind) -> ErrorKind:
        raise NotImplementedError  # 1:1 table


class LevelSource(StrEnum):
    MICROPHONE = "microphone"
    SPEAKER = "speaker"


@dataclass(frozen=True)
class ClipRendition:
    clip: str
    """Pool entry, e.g. ``acolyte/AcolyteWhat3``."""


@dataclass(frozen=True)
class LineRendition:
    text: str
    """The event's fallback line, spoken in the active persona's voice."""


CueRendition: TypeAlias = ClipRendition | LineRendition


@dataclass(frozen=True)
class TurnTimings:
    """Monotonic timestamps (seconds, from the Clock port) for the per-turn latency log."""

    activation: float
    endpoint: float | None
    transcript: float | None
    routed: float | None
    first_token: float | None
    first_sentence_synthesized: float | None
    first_audio: float | None
    ended: float


@dataclass(frozen=True)
class StateChanged:
    state: State


@dataclass(frozen=True)
class SleepChanged:
    asleep: bool


@dataclass(frozen=True)
class PersonaChanged:
    persona: PersonaName
    display_name: str
    voice: VoiceId


@dataclass(frozen=True)
class SessionStarted:
    persona: PersonaName
    context_lost: bool
    """True when this replaces a crashed session (the user is told)."""


@dataclass(frozen=True)
class WakeDetected:
    score: float


@dataclass(frozen=True)
class TurnStarted:
    turn: TurnId
    activation: Activation


@dataclass(frozen=True)
class CaptureEnded:
    turn: TurnId
    end: CaptureEnd
    voiced_ms: int
    captured_ms: int


@dataclass(frozen=True)
class Transcribed:
    turn: TurnId
    raw: str
    text: str
    """Normalized: wake phrase stripped, whitespace collapsed."""


@dataclass(frozen=True)
class Routed:
    turn: TurnId
    route: Route


@dataclass(frozen=True)
class CuePlayed:
    turn: TurnId | None
    cue: CueEvent
    rendition: CueRendition


@dataclass(frozen=True)
class SentenceQueued:
    turn: TurnId | None
    index: int
    text: str
    voice: VoiceId


@dataclass(frozen=True)
class SentenceSpoken:
    """Emitted when the sentence's audio starts playing."""

    turn: TurnId | None
    index: int
    text: str
    voice: VoiceId


@dataclass(frozen=True)
class ToolAllowed:
    turn: TurnId
    call: ToolCall


@dataclass(frozen=True)
class SafetyRefused:
    turn: TurnId
    call: ToolCall
    category: DenyCategory


@dataclass(frozen=True)
class ActionPerformed:
    turn: TurnId
    intent: DesktopIntent
    result: ActionResult


@dataclass(frozen=True)
class ErrorOccurred:
    turn: TurnId | None
    kind: ErrorKind
    detail: str
    spoken: str


@dataclass(frozen=True)
class TurnFinished:
    turn: TurnId
    outcome: TurnOutcome
    timings: TurnTimings


@dataclass(frozen=True)
class Level:
    """Coalesced by subscriptions (latest wins), never queued; see ``core.bus``."""

    source: LevelSource
    rms: float


DomainEvent: TypeAlias = (
    StateChanged
    | SleepChanged
    | PersonaChanged
    | SessionStarted
    | WakeDetected
    | TurnStarted
    | CaptureEnded
    | Transcribed
    | Routed
    | CuePlayed
    | SentenceQueued
    | SentenceSpoken
    | ToolAllowed
    | SafetyRefused
    | ActionPerformed
    | ErrorOccurred
    | TurnFinished
    | Level
)


# --------------------------------------------------------------------------- status snapshot


@dataclass(frozen=True)
class PersonaStatus:
    name: PersonaName
    display_name: str
    availability: Availability
    session_open: bool


@dataclass(frozen=True)
class Status:
    state: State
    asleep: bool
    persona: PersonaName
    personas: tuple[PersonaStatus, ...]
    turn: TurnId | None
