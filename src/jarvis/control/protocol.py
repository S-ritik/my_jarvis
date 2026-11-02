"""Control Socket wire schema (protocol version 1): the single source of truth.

Every request, reply and event on the socket is a closed type in this module, and this
module is the only place a wire field name or command name is spelled. The server
(``control.server``), the ``jarvis ctl`` client (``control.client``) and the HUD
(``hud.link``) all import it; none of them import each other's internals. This module
imports nothing from ``jarvis.core`` -- the domain<->wire mapping is ``control.mapping``.

Transport: Unix stream socket ``$XDG_RUNTIME_DIR/jarvis.sock`` (0600, peer uid checked),
newline-delimited UTF-8 JSON, one object per line, max 64 KiB per line.

Client -> server (``id`` is chosen by the client and echoed)::

    {"id": "1", "cmd": "talk"}                     stop | sleep | wake | toggle-sleep | status | subscribe
    {"id": "2", "cmd": "persona", "name": "oracle"}
    {"id": "3", "cmd": "ask", "text": "what time is it"}
    {"id": "4", "cmd": "mute"}                     alias of sleep (unmute = wake)

Server -> client::

    {"type": "reply", "id": "1", "ok": true}
    {"type": "reply", "id": "9", "ok": true, "status": {...}}                 (status)
    {"type": "reply", "id": "2", "ok": false, "error": {"code": "unavailable", "message": "..."}}
    {"type": "hello", "id": "5", "protocol": 1, "status": {...}}              (reply to subscribe)
    {"type": "event", "seq": 42, "event": "state", "state": "thinking"}
    {"type": "overflow", "last_seq": 97}                                      (then the server closes)

    status = {"state": "idle", "asleep": false, "persona": "jarvis",
              "personas": [{"name": "oracle", "display_name": "Oracle", "available": false,
                            "reason": "Antigravity is not installed."}, ...]}

Connections: a *command* connection sends requests and reads one reply per request, in
order. A *subscription* connection sends ``subscribe`` once; the server answers ``hello``
and then only pushes events until either side closes (further client lines are ignored).

Versioning: additive changes (new optional field, new event kind, new string value of an
open field such as ``cue`` or ``outcome``) keep ``PROTOCOL_VERSION``; removing/renaming a
field or changing a closed enum (``WireState``) bumps it. Clients decode unknown event
kinds to ``UnknownEvent`` and ignore them; the server answers unknown commands with
``unknown_command``.

Adding a command: add a dataclass with a ``CMD`` class constant (and at most one ``str``
field, which is also its ``jarvis ctl`` argument) to ``CommandBody``. Decoding, encoding
and ``jarvis ctl`` parsing are derived from the union; ``control.mapping`` then fails type
checking until the command is mapped.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import ClassVar, Final, TypeAlias

PROTOCOL_VERSION: Final = 1
MAX_LINE_BYTES: Final = 64 * 1024

# --------------------------------------------------------------------------- requests


@dataclass(frozen=True)
class TalkCmd:
    CMD: ClassVar[str] = "talk"


@dataclass(frozen=True)
class StopCmd:
    CMD: ClassVar[str] = "stop"


@dataclass(frozen=True)
class SleepCmd:
    CMD: ClassVar[str] = "sleep"


@dataclass(frozen=True)
class WakeCmd:
    CMD: ClassVar[str] = "wake"


@dataclass(frozen=True)
class ToggleSleepCmd:
    CMD: ClassVar[str] = "toggle-sleep"


@dataclass(frozen=True)
class PersonaCmd:
    CMD: ClassVar[str] = "persona"
    name: str


@dataclass(frozen=True)
class AskCmd:
    CMD: ClassVar[str] = "ask"
    text: str


@dataclass(frozen=True)
class StatusCmd:
    CMD: ClassVar[str] = "status"


@dataclass(frozen=True)
class SubscribeCmd:
    CMD: ClassVar[str] = "subscribe"


CommandBody: TypeAlias = TalkCmd | StopCmd | SleepCmd | WakeCmd | ToggleSleepCmd | PersonaCmd | AskCmd
"""Requests that become a core ``Command`` (see ``control.mapping.command_from_wire``)."""

RequestBody: TypeAlias = CommandBody | StatusCmd | SubscribeCmd

ALIASES: Final[Mapping[str, str]] = {"mute": "sleep", "unmute": "wake"}


@dataclass(frozen=True)
class Request:
    id: str
    body: RequestBody


# --------------------------------------------------------------------------- shared values


class WireState(StrEnum):
    """Closed: changing it bumps PROTOCOL_VERSION."""

    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


@dataclass(frozen=True)
class WirePersona:
    name: str
    display_name: str
    available: bool
    reason: str | None
    """Present only when ``available`` is false."""


@dataclass(frozen=True)
class WireStatus:
    state: WireState
    asleep: bool
    persona: str
    personas: tuple[WirePersona, ...]


class ErrorCode(StrEnum):
    BAD_REQUEST = "bad_request"
    UNKNOWN_COMMAND = "unknown_command"
    UNAVAILABLE = "unavailable"
    BUSY = "busy"
    INTERNAL = "internal"


@dataclass(frozen=True)
class WireError:
    code: ErrorCode
    message: str


# --------------------------------------------------------------------------- events (open set of kinds)


@dataclass(frozen=True)
class StateEvent:
    KIND: ClassVar[str] = "state"
    state: WireState


@dataclass(frozen=True)
class SleepEvent:
    KIND: ClassVar[str] = "sleep"
    asleep: bool


@dataclass(frozen=True)
class PersonaEvent:
    KIND: ClassVar[str] = "persona"
    name: str
    display_name: str


@dataclass(frozen=True)
class TurnStartedEvent:
    KIND: ClassVar[str] = "turn_started"
    turn: int
    activation: str


@dataclass(frozen=True)
class TranscriptEvent:
    KIND: ClassVar[str] = "transcript"
    turn: int
    text: str


@dataclass(frozen=True)
class CueWireEvent:
    KIND: ClassVar[str] = "cue"
    cue: str
    clip: str | None
    """None when the fallback line was spoken instead."""


@dataclass(frozen=True)
class SentenceEvent:
    """A sentence started playing."""

    KIND: ClassVar[str] = "sentence"
    turn: int | None
    text: str


@dataclass(frozen=True)
class ActionEvent:
    KIND: ClassVar[str] = "action"
    turn: int
    action: str
    ok: bool


@dataclass(frozen=True)
class SafetyEvent:
    KIND: ClassVar[str] = "safety"
    turn: int
    category: str
    tool: str


@dataclass(frozen=True)
class ErrorEvent:
    KIND: ClassVar[str] = "error"
    turn: int | None
    kind: str
    message: str


@dataclass(frozen=True)
class LevelEvent:
    """Rate-limited per subscriber (``ControlSettings.level_max_hz``)."""

    KIND: ClassVar[str] = "level"
    source: str
    rms: float


@dataclass(frozen=True)
class TurnEndedEvent:
    KIND: ClassVar[str] = "turn_ended"
    turn: int
    outcome: str


@dataclass(frozen=True)
class UnknownEvent:
    """Decode-only: an event kind this client version does not know. Ignore it."""

    kind: str


WireEvent: TypeAlias = (
    StateEvent
    | SleepEvent
    | PersonaEvent
    | TurnStartedEvent
    | TranscriptEvent
    | CueWireEvent
    | SentenceEvent
    | ActionEvent
    | SafetyEvent
    | ErrorEvent
    | LevelEvent
    | TurnEndedEvent
    | UnknownEvent
)


# --------------------------------------------------------------------------- server -> client messages


@dataclass(frozen=True)
class OkReply:
    id: str
    status: WireStatus | None
    """Set only in the reply to ``status``."""


@dataclass(frozen=True)
class ErrorReply:
    id: str | None
    """None when the request line was too malformed to carry an id."""
    error: WireError


@dataclass(frozen=True)
class Hello:
    id: str
    protocol: int
    status: WireStatus


@dataclass(frozen=True)
class EventMessage:
    seq: int
    event: WireEvent


@dataclass(frozen=True)
class Overflow:
    last_seq: int


ServerMessage: TypeAlias = OkReply | ErrorReply | Hello | EventMessage | Overflow


# --------------------------------------------------------------------------- codec


def encode_request(request: Request) -> bytes:
    raise NotImplementedError  # {"id": id, "cmd": body.CMD, **asdict(body)} + b"\n"


def decode_request(line: bytes) -> Request | ErrorReply:
    """Never raises. Bad JSON / non-object / missing or non-string ``id`` -> ``bad_request``;
    unknown ``cmd`` (after ``ALIASES``) -> ``unknown_command``; missing/wrong-typed argument
    -> ``bad_request``; over ``MAX_LINE_BYTES`` -> ``bad_request``."""
    raise NotImplementedError
    # registry derived once: {cls.CMD: cls for cls in typing.get_args(RequestBody)}


def request_from_argv(argv: Sequence[str], request_id: str) -> Request | ErrorReply:
    """``jarvis ctl`` grammar, derived from the same registry: ``argv[0]`` is the command
    (aliases allowed); a command with one field takes the remaining words joined by spaces
    (``ctl ask what time is it``); a command with no field rejects extra words."""
    raise NotImplementedError


def encode_server(message: ServerMessage) -> bytes:
    raise NotImplementedError


def decode_server(line: bytes) -> ServerMessage | None:
    """Client side. Unknown event kinds -> ``EventMessage(seq, UnknownEvent(kind))``;
    unknown extra fields ignored; structurally invalid line -> None (client logs it)."""
    raise NotImplementedError
