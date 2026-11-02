"""Domain <-> wire mapping: the one place core vocabulary meets the Control Socket schema.

Every function is an exhaustive ``match`` (``assert_never``), so a new ``Command``,
``DomainEvent`` or ``RejectReason`` variant fails type checking here until it is decided
how (or whether) it appears on the wire. Internal-only data (PCM, exceptions, raw tool
inputs, prompts) has no wire field and therefore cannot leak.
"""

from __future__ import annotations

from jarvis.control.protocol import (
    CommandBody,
    ErrorCode,
    ErrorReply,
    OkReply,
    WireEvent,
    WireStatus,
)
from jarvis.core.vocabulary import Command, CommandResult, DomainEvent, Status


def command_from_wire(body: CommandBody) -> Command:
    raise NotImplementedError
    # TalkCmd -> Talk(); StopCmd -> Stop(); SleepCmd -> Sleep(); WakeCmd -> Wake();
    # ToggleSleepCmd -> ToggleSleep(); PersonaCmd(n) -> SwitchPersona(n); AskCmd(t) -> Ask(t)


def reply_from_result(request_id: str, result: CommandResult) -> OkReply | ErrorReply:
    raise NotImplementedError
    # Accepted -> OkReply(id, None)
    # Rejected(ASLEEP | PERSONA_UNAVAILABLE | SHUTTING_DOWN) -> ErrorCode.UNAVAILABLE
    # Rejected(UNKNOWN_PERSONA | EMPTY_REQUEST)            -> ErrorCode.BAD_REQUEST


def status_to_wire(status: Status) -> WireStatus:
    raise NotImplementedError


def event_to_wire(event: DomainEvent) -> WireEvent | None:
    """None = not published on the socket (e.g. ``Routed``, ``SentenceQueued``,
    ``CaptureEnded``, ``ToolAllowed``, ``SessionStarted``, ``WakeDetected``; they are
    still in the journal)."""
    raise NotImplementedError
    # StateChanged(s)            -> StateEvent(WireState(s.value))
    # SleepChanged(a)            -> SleepEvent(a)
    # PersonaChanged(p, d, _)    -> PersonaEvent(p, d)
    # TurnStarted(t, a)          -> TurnStartedEvent(t, a.value)
    # Transcribed(t, _, text)    -> TranscriptEvent(t, text)
    # CuePlayed(_, c, r)         -> CueWireEvent(c.value, r.clip if ClipRendition else None)
    # SentenceSpoken(t, _, x, _) -> SentenceEvent(t, x)
    # ActionPerformed(t, i, r)   -> ActionEvent(t, _action_name(i), isinstance(r, ActionDone))
    #                               (_action_name: exhaustive match -> 'volume_up', 'media_pause', 'launch:firefox', ...;
    #                                never derived from Python class names, so refactors don't change the wire)
    # SafetyRefused(t, call, c)  -> SafetyEvent(t, c.value, call.vendor_name)
    # ErrorOccurred(t, k, _, s)  -> ErrorEvent(t, k.value, s)
    # Level(src, rms)            -> LevelEvent(src.value, rms)
    # TurnFinished(t, o, _)      -> TurnEndedEvent(t, o.value)
    # others                     -> None


__all__ = ["command_from_wire", "reply_from_result", "status_to_wire", "event_to_wire", "ErrorCode"]
