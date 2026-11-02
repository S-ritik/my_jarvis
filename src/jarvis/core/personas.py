"""Personas and their Brain Sessions for one voice run.

Knowledge owned here: the persona table and alias lookup; which persona is active;
backend availability (probed at boot, re-probed when switching to an unavailable one);
one session per persona, opened lazily (the default one at boot); what a session is
opened with (composed prompt + ``BrainContext`` preamble and tools + the core's gate),
narrowed by the backend's ``capabilities`` (``gates_tools=False`` -> no built-ins;
``custom_tools=False`` -> no custom tools) so no adapter can open an ungated shell;
turn hygiene on the port (one turn in flight, always iterated to its terminal event);
abandoning a turn (native interrupt when ``interruptible``, otherwise drain-and-discard,
session kept alive); brain-side timeouts on the injected ``Clock``; crash detection and
reopen-on-next-turn with ``context_lost``; closing every session on exit.

It never touches speech, state or events. It *posts* ``BrainProgress`` to the core.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TypeAlias

from jarvis.brain.port import (
    Availability,
    BackendKind,
    BrainBackend,
    BrainEvent,
    PermissionGate,
    Unavailable,
)
from jarvis.core.ports import BrainContext, Clock
from jarvis.core.vocabulary import Persona, PersonaName, PersonaStatus, TurnId
from jarvis.settings import BrainSettings, SafetySettings


@dataclass(frozen=True)
class BrainProgress:
    """A brain stream event for a turn. Events of abandoned turns are never posted."""

    turn: TurnId
    event: BrainEvent


@dataclass(frozen=True)
class SessionOpened:
    persona: PersonaName
    context_lost: bool


PersonaPost: TypeAlias = Callable[[BrainProgress | SessionOpened], None]


@dataclass(frozen=True)
class Switched:
    persona: Persona


@dataclass(frozen=True)
class UnknownPersona:
    spoken: str


@dataclass(frozen=True)
class PersonaUnavailable:
    persona: Persona
    why: Unavailable


SwitchResult: TypeAlias = Switched | UnknownPersona | PersonaUnavailable


class Personas:
    def __init__(
        self,
        table: tuple[Persona, ...],
        default: PersonaName,
        backends: Mapping[BackendKind, BrainBackend],
        context: BrainContext,
        gate_for: Callable[[PersonaName], PermissionGate],
        clock: Clock,
        brain: BrainSettings,
        safety: SafetySettings,
        post: PersonaPost,
    ) -> None:
        raise NotImplementedError

    @property
    def active(self) -> Persona:
        raise NotImplementedError

    @property
    def aliases(self) -> Mapping[str, PersonaName]:
        """Lowercase alias -> persona, for the Router."""
        raise NotImplementedError

    async def boot(self) -> Availability:
        """Probe every backend in use (concurrently) and open the default persona's session
        so the first turn is warm. Returns the default persona's availability; an
        ``Unavailable`` here is spoken after the boot cue ("Claude Code is logged out")."""
        raise NotImplementedError

    async def switch(self, spoken: str) -> SwitchResult:
        """Resolve a name/alias, re-probe if it was unavailable, make it active and start
        warming its session in the background (lazy start = first switch or first turn).
        Other personas' sessions are untouched."""
        raise NotImplementedError

    def begin_turn(self, turn: TurnId, text: str) -> None:
        """Send ``text`` to the active persona's session as ``turn``.

        Runs as a background task owned by this object:
          await previous turn of this session reaching its terminal event (bounded)
          session = existing or await open(spec)  # crashed -> reopen, post SessionOpened(context_lost=True)
              where caps = backend.capabilities and spec = SessionSpec(
                  builtins = safety.allowlist if caps.gates_tools else frozenset(),
                  tools    = context.tools()  if caps.custom_tools else (), ...)
          async for ev in session.send(text):     # raced against clock deadlines:
              if turn not abandoned: post(BrainProgress(turn, ev))     #   first event, whole turn
              if ev is terminal: break
          deadline hit -> abandon + post(BrainProgress(turn, BrainFailed(TIMEOUT)))
          BrainFailed(CRASHED) -> forget the session; next begin_turn reopens it
        """
        raise NotImplementedError

    def abandon_turn(self) -> None:
        """Detach the in-flight turn (``stop``, barge-in, safety deny, sleep, shutdown).

        From now on its events are dropped and its tool calls are answered
        ``Deny(TURN_CANCELLED)`` by the core's gate. ``interrupt()`` is called if the
        session is interruptible; otherwise the stream is drained and discarded. Either
        way the pump keeps iterating to the terminal event so the session stays usable.
        """
        raise NotImplementedError

    def turn_of(self, persona: PersonaName) -> TurnId | None:
        """The live (not abandoned) turn this persona's session is serving, if any.
        The core's gate uses it to tag or cancel tool calls."""
        raise NotImplementedError

    def statuses(self) -> tuple[PersonaStatus, ...]:
        raise NotImplementedError

    async def close(self) -> None:
        """Abandon any turn and close every open session (clean exit; nothing resumes next run)."""
        raise NotImplementedError
