"""The Assistant Core (seam 1): one actor that owns the turn.

Public surface: ``AssistantCore`` (constructor, ``async with``, ``command``, ``subscribe``,
``status``). That is the whole seam the daemon, the Control Socket and the tests use.

How it works (the part a contributor must not break):

* **One inbox, one task.** Every input -- microphone frames, commands, brain progress,
  gate outcomes, speech progress, action/transcription results -- is a value put on one
  ``asyncio.Queue``. A single actor task takes them one at a time and is the only code
  that mutates turn state and the only code that publishes domain events. "One ordered
  stream" is therefore true by construction, not by locking.
* **Policies are consulted in-line.** ``Listener``, ``Router``, ``SafetyGate``,
  ``CueBoard`` (inside ``Speech``) and the chunker (inside ``Speech``) are synchronous or
  per-frame and called from the actor. Their decisions are deterministic: listening time
  is samples, cue randomness is ``Ports.rng``, brain time is ``Ports.clock``.
* **Effects are tasks that post back.** Transcription, desktop actions, brain turns
  (inside ``Personas``), synthesis and playback (inside ``Speech``) run concurrently and
  post results tagged with their ``TurnId``. Staleness is checked in exactly one place,
  ``_handle``, *before* dispatch (``_turn_of(item)`` is an exhaustive match over the
  inbox union): a handler never sees a result from a turn that is no longer current, and
  a new turn-tagged input type cannot be added without deciding its turn (the match is
  exhaustive). Flush also *cancels* the turn's tasks; the drop only covers results that
  were already queued, so stopping work and ignoring leftovers are not two policies.
* **One flush.** ``_flush_turn`` = ``speech.flush()`` + ``personas.abandon_turn()`` +
  cancel the turn's tasks + forget the turn. ``stop``, barge-in, safety deny, sleep,
  shutdown and ``ask``-over-a-turn all call it; nothing else stops audio or brains.

The table of *when* things happen (state transitions, mic gating, which cue when) is in
this file and only here. *How* is in the policy and effect modules.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import TracebackType
from collections.abc import Coroutine
from typing import Any, Self, TypeAlias

from jarvis.audio import AudioFrame
from jarvis.brain.port import (
    EditFile,
    PermissionGate,
    RunShell,
    ToolAction,
    ToolCall,
    ToolVerdict,
    WriteFile,
)
from jarvis.core.bus import EventBus, EventSubscription
from jarvis.core.personas import BrainProgress, Personas, SessionOpened, SwitchResult
from jarvis.core.ports import Ports
from jarvis.core.speech import SpeechProgress
from jarvis.core.vocabulary import (
    ActionResult,
    Activation,
    Command,
    CommandResult,
    DesktopIntent,
    ErrorKind,
    PersonaName,
    State,
    Status,
    TurnId,
    TurnOutcome,
)
from jarvis.settings import Settings

_ACTING_TOOLS: tuple[type[ToolAction], ...] = (RunShell, WriteFile, EditFile)
"""``task_completed`` plays after a brain turn in which one of these ran (spec "When each cue plays")."""


class AssistantCore:
    """The JARVIS turn state machine. See module docstring.

    Lifecycle::

        core = AssistantCore(ports, settings)
        sub = core.subscribe()          # optional, before start: sees the boot sequence
        async with core:                # boot: cues loaded, default session warm, mic open, `boot` cue
            await core.command(Ask("what time is it"))
        # exit: turn flushed, `shutdown` cue played, mic closed, sessions closed, subscriptions ended

    Commands sent before ``async with`` are answered once boot completes.
    """

    def __init__(self, ports: Ports, settings: Settings) -> None:
        raise NotImplementedError
        # self._ports, self._settings = ports, settings
        # self._inbox: asyncio.Queue[_Input] = asyncio.Queue()
        # self._bus = EventBus(ports.clock.monotonic)
        # self._gate = SafetyGate(settings.safety)
        # self._listener = Listener(settings.listening, ports.wake, ports.vad)
        # self._personas = Personas(settings.personas, settings.default_persona, ports.brains,
        #                           ports.context, self._gate_for, ports.clock, settings.brain,
        #                           settings.safety, post=self._inbox.put_nowait)
        # self._speech / self._router are built during boot (need loaded cues / app directory)
        # self._state = State.IDLE; self._asleep = settings.start_asleep; self._turn: _Turn | None = None

    async def __aenter__(self) -> Self:
        raise NotImplementedError
        # tg = TaskGroup; start actor task (self._run_actor) and speech.run()
        # cues = await CueBoard.load(settings.cues, ports.clips, ports.rng)
        # self._speech = Speech(ports.synthesizer, ports.player, cues, settings.speech, post=inbox.put_nowait)
        # self._router = Router(RouteContext(personas.aliases, await ports.desktop.app_directory()))
        # default_availability = await personas.boot()            # default session warm
        # if not asleep: self._open_mic()                          # wake listening live
        # post(_Booted(default_availability)) and await it:        # actor publishes StateChanged(IDLE),
        #     PersonaChanged(default), plays `boot` cue, then speaks an Unavailable warning if any

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        raise NotImplementedError
        # done = Future(); inbox.put(_ShutdownIn(done)); await done
        #   actor: _flush_turn(INTERRUPTED); close mic; speech.cue(None, SHUTDOWN, voice);
        #          await Drained (bounded by clock deadline); await personas.close();
        #          bus.end_all(SHUTDOWN); stop actor
        # cancel speech.run; leave task group

    async def command(self, command: Command) -> CommandResult:
        """Apply a control command. Returns once the actor has accepted or rejected it
        (for ``Ask``: once the turn has started, not when it ends)."""
        raise NotImplementedError
        # reply = loop.create_future(); inbox.put_nowait(_CommandIn(command, reply)); return await reply

    def subscribe(self, *, capacity: int | None = 256) -> EventSubscription:
        """Subscribe to the ordered domain-event stream. ``snapshot`` is the status at the
        instant of subscribing; the first envelope is the first event after it."""
        raise NotImplementedError  # return self._bus.subscribe(self.status(), capacity)

    def status(self) -> Status:
        raise NotImplementedError

    # ------------------------------------------------------------------ actor (private)

    async def _run_actor(self) -> None:
        raise NotImplementedError
        # while True:
        #     item = await inbox.get()
        #     try: await self._handle(item)
        #     except Exception as e:  # a bug in a handler must not kill the daemon
        #         log; publish ErrorOccurred(turn, INTERNAL, repr(e), phrases.internal_error());
        #         _flush_turn(FAILED); speech.line(...)

    async def _handle(self, item: _Input) -> None:
        raise NotImplementedError
        # tagged = _turn_of(item)
        # if tagged is not None and (self._turn is None or tagged != self._turn.id): return   # stale: the ONE check
        # match item:   (exhaustive; assert_never)
        #   _FrameIn            -> _on_frame
        #   _CommandIn          -> _on_command
        #   _TranscriptIn       -> _on_transcript
        #   _ActionIn           -> _on_action
        #   _GateIn             -> _on_gate
        #   _SwitchIn           -> _on_switch
        #   _TaskFailed         -> _on_task_failed
        #   BrainProgress       -> _on_brain
        #   SessionOpened       -> publish SessionStarted; if context_lost: speech.line(CONTEXT_LOST)
        #   SpeechProgress      -> _on_speech
        #   _BootedIn/_ShutdownIn -> lifecycle

    async def _on_frame(self, frame: AudioFrame) -> None:
        raise NotImplementedError
        # heard = await listener.hear(frame)     # listener is paused unless Idle/Listening
        # if state is LISTENING: publish Level(MICROPHONE, rms(frame))
        # match heard:
        #   Nothing():   pass
        #   WakeHeard(s): publish WakeDetected(s); _begin_turn(WAKE_WORD); -> LISTENING
        #   AckDue():    speech.cue(turn, WAKE_ACK, voice)            # listener muted itself
        #   Utterance(a, end, v, c): publish CaptureEnded; -> THINKING; _spawn(turn, transcribe(a) -> _TranscriptIn)
        #   NoSpeech():  _finish(NO_SPEECH)                            # silently

    async def _on_command(self, command: Command, reply: asyncio.Future[CommandResult]) -> None:
        raise NotImplementedError
        # match command:
        #   Talk():  asleep -> Rejected(ASLEEP)
        #            turn active -> _flush_turn(INTERRUPTED)          # barge-in from Thinking/Speaking
        #            _begin_turn(PUSH_TO_TALK); listener.start_capture(); -> LISTENING   (no ack cue)
        #   Stop():  _flush_turn(INTERRUPTED) if turn; -> IDLE; listener.idle() unless asleep
        #   Sleep(): _flush_turn(INTERRUPTED) if turn; _close_mic(); asleep=True; publish SleepChanged(True)
        #   Wake():  if asleep: _open_mic(); asleep=False; listener.idle(); publish SleepChanged(False)
        #   ToggleSleep(): Sleep() if not asleep else Wake()
        #   SwitchPersona(name): spawn personas.switch(name) -> _SwitchIn(result, reply, turn=None)
        #   Ask(text): blank -> Rejected(EMPTY_REQUEST)
        #              turn active -> _flush_turn(INTERRUPTED)
        #              _begin_turn(TYPED); -> THINKING; _route(turn, raw=text)
        #   reply.set_result(Accepted()) unless rejected/deferred

    def _route(self, raw: str) -> None:
        raise NotImplementedError
        # text, route = router.route(raw); publish Transcribed(turn, raw, text); publish Routed(turn, route)
        # match route:
        #   Dismiss(_):                       _finish(DISMISSED)                  # silent
        #   Control(SwitchPersona(name)):     spawn switch -> _SwitchIn(result, reply=None, turn)
        #   Control(Sleep()):                 _finish(ACTED); then as Sleep command
        #   Act(intent):                      _spawn(turn, perform(intent) -> _ActionIn)   # no task_received cue
        #   Answer(q):                        speech.line(turn, phrases.local_answer(q, clock.now()), voice)
        #                                     turn.outcome = ANSWERED_LOCALLY; turn.awaiting_drain = True
        #   Think(text):                      speech.cue(turn, TASK_RECEIVED, voice)
        #                                     personas.begin_turn(turn, text)

    def _on_action(self, turn: TurnId, intent: DesktopIntent, result: ActionResult) -> None:
        raise NotImplementedError
        # (staleness already handled in _handle) publish ActionPerformed
        # ActionDone   -> speech.cue(turn, TASK_COMPLETED, voice); outcome ACTED
        # ActionFailed -> speech.line(turn, phrases.action_failed(f), voice);
        #                 publish ErrorOccurred(ACTION_FAILED); outcome FAILED
        # turn.awaiting_drain = True

    def _on_switch(self, result: SwitchResult, reply: asyncio.Future[CommandResult] | None, turn: TurnId | None) -> None:
        raise NotImplementedError
        # Switched(p):           publish PersonaChanged(p.name, p.voice); speech.line(turn, persona_switched(p), p.voice)
        # UnknownPersona(s):     reply Rejected(UNKNOWN_PERSONA)  (voice path never produces this: Router declined)
        # PersonaUnavailable(p, why): speech.line(turn, persona_unavailable(p, why.reason), active voice)
        #                        publish ErrorOccurred(PERSONA_UNAVAILABLE); reply Rejected(PERSONA_UNAVAILABLE)
        # if turn: outcome ANSWERED_LOCALLY / FAILED; awaiting_drain = True

    def _on_brain(self, progress: BrainProgress) -> None:
        raise NotImplementedError
        # turn.refused -> drop (deltas still queued behind a deny); staleness handled in _handle
        # TextDelta(t):      timings.first_token; speech.text(turn, t, voice)
        # ToolFinished(id, ok): if ok and isinstance(allowed[id], _ACTING_TOOLS): turn.acted = True
        # TurnEnded(_):      speech.end_of_text(turn, voice)
        #                    if turn.acted: speech.cue(turn, TASK_COMPLETED, voice)
        #                    outcome = ACTED if acted else ANSWERED; awaiting_drain = True
        # BrainFailed(err):  speech.end_of_text(...) is skipped (remainder dropped);
        #                    speech.line(turn, phrases.brain_error(err, persona), voice)
        #                    publish ErrorOccurred(ErrorKind.of_brain(err.kind)); outcome FAILED; awaiting_drain = True

    def _gate_for(self, persona: PersonaName) -> PermissionGate:
        """The permission callback handed to this persona's sessions (see ``Personas``).

        Runs on the event loop inside the backend's task, *not* in the actor. It computes
        the verdict purely and posts the outcome, so the consequences appear in the
        stream in inbox order, after the text the brain streamed before the call.
        """

        async def gate(call: ToolCall) -> ToolVerdict:
            raise NotImplementedError
            # turn = personas.turn_of(persona)
            # if turn is None or self._turn is None or turn != self._turn.id:
            #     return Deny(TURN_CANCELLED, "The user cancelled this request. Stop.")
            # verdict = self._gate.check(call.action)
            # inbox.put_nowait(_GateIn(turn, persona, call, verdict))
            # return verdict

        return gate

    def _on_gate(self, turn: TurnId, persona: PersonaName, call: ToolCall, verdict: ToolVerdict) -> None:
        raise NotImplementedError
        # (staleness handled in _handle)
        # Allow():  publish ToolAllowed(turn, call); allowed[call.call_id] = call.action
        # Deny(category):  (TURN_CANCELLED never reaches here)
        #   publish SafetyRefused(turn, call, category)
        #   spawn ports.audit.record(AuditEntry(clock.now(), turn, persona, category, call))   # not turn-scoped
        #   speech.flush(); personas.abandon_turn(); turn.refused = True
        #   speech.cue(turn, SAFETY_BLOCKED, voice); speech.line(turn, SAFETY_LINE, voice)
        #   outcome REFUSED; awaiting_drain = True

    def _on_speech(self, progress: SpeechProgress) -> None:
        raise NotImplementedError
        # SentenceReady  -> publish SentenceQueued
        # Synthesized    -> timings.first_sentence_synthesized (first only)
        # SentenceStarted-> if turn and state != SPEAKING: -> SPEAKING (published first); publish SentenceSpoken;
        #                   timings.first_audio
        # CueStarted     -> publish CuePlayed
        # SpeakerLevel   -> publish Level(SPEAKER, rms)
        # SpeechFailed   -> publish ErrorOccurred(SPEECH_FAILED) (log-only phrasing; nothing to speak with)
        # Drained        -> if speech.busy: ignore (stale)
        #                   listener.speaker_drained()                      # 250 ms hangover, lifts ack mute
        #                   if turn and turn.awaiting_drain: _finish(turn.outcome)

    def _spawn(self, turn: TurnId, work: Coroutine[Any, Any, _Input]) -> None:
        """The only way a handler starts slow work (transcribe, desktop action, persona switch).

        Runs ``work`` as a task registered on the current turn (so ``_flush_turn`` cancels it)
        and posts its result value to the inbox; an exception becomes ``_TaskFailed``. Handlers
        never ``await`` a port themselves (per-frame scorers inside the Listener excepted).
        """
        raise NotImplementedError

    def _begin_turn(self, activation: Activation) -> TurnId:
        raise NotImplementedError  # new id; timings.activation = clock.monotonic(); publish TurnStarted

    def _finish(self, outcome: TurnOutcome) -> None:
        raise NotImplementedError
        # publish TurnFinished(turn, outcome, timings); turn = None; -> IDLE
        # if not asleep: listener.idle()

    def _flush_turn(self, outcome: TurnOutcome) -> None:
        """The one flush: silence, forget queued speech, detach the brain turn, cancel the
        turn's tasks, finish the turn. Callers then set the next state."""
        raise NotImplementedError
        # speech.flush(); personas.abandon_turn(); for t in turn.tasks: t.cancel(); _finish(outcome)

    def _set_state(self, state: State) -> None:
        raise NotImplementedError  # if changed: publish StateChanged(state); Thinking/Speaking -> listener.pause()

    def _open_mic(self) -> None:
        raise NotImplementedError
        # self._mic_task = create_task(pump): async with ports.microphone.open() as frames:
        #                                          async for f in frames: inbox.put_nowait(_FrameIn(f))

    def _close_mic(self) -> None:
        raise NotImplementedError  # cancel the pump task: leaving the context closes the device


# --------------------------------------------------------------------------- inbox values (private)


@dataclass(frozen=True, eq=False)
class _FrameIn:
    frame: AudioFrame


@dataclass(frozen=True, eq=False)
class _CommandIn:
    command: Command
    reply: asyncio.Future[CommandResult]


@dataclass(frozen=True)
class _TranscriptIn:
    turn: TurnId
    raw: str


@dataclass(frozen=True)
class _ActionIn:
    turn: TurnId
    intent: DesktopIntent
    result: ActionResult


@dataclass(frozen=True)
class _GateIn:
    turn: TurnId
    persona: PersonaName
    call: ToolCall
    verdict: ToolVerdict


@dataclass(frozen=True, eq=False)
class _SwitchIn:
    result: SwitchResult
    reply: asyncio.Future[CommandResult] | None
    turn: TurnId | None


@dataclass(frozen=True)
class _TaskFailed:
    """A turn task (transcribe, perform) raised: contained, spoken, turn ends FAILED."""

    turn: TurnId
    kind: ErrorKind
    detail: str


@dataclass(frozen=True, eq=False)
class _ShutdownIn:
    done: asyncio.Future[None]


@dataclass(eq=False)
class _Turn:
    id: TurnId
    activation: Activation
    persona: PersonaName
    tasks: set[asyncio.Task[None]] = field(default_factory=set)
    allowed: dict[str, ToolAction] = field(default_factory=dict)
    acted: bool = False
    refused: bool = False
    awaiting_drain: bool = False
    outcome: TurnOutcome = TurnOutcome.ANSWERED


_Input: TypeAlias = (
    _FrameIn
    | _CommandIn
    | _TranscriptIn
    | _ActionIn
    | _GateIn
    | _SwitchIn
    | _TaskFailed
    | _ShutdownIn
    | BrainProgress
    | SessionOpened
    | SpeechProgress
)


def _turn_of(item: _Input) -> TurnId | None:
    """The turn an inbox value belongs to, or ``None`` if it is not turn-scoped.

    The single staleness rule lives on this function: ``_handle`` drops any value whose
    turn is not the current one *before* dispatch. Exhaustive on purpose -- adding an
    ``_Input`` variant fails type checking until its turn scoping is decided here.
    """
    raise NotImplementedError
    # match item:
    #   _TranscriptIn() | _ActionIn() | _GateIn() | _TaskFailed() | BrainProgress():  return item.turn
    #   _SwitchIn():                                  return item.turn          # None for a ctl switch
    #   SentenceReady() | Synthesized() | SentenceStarted() | CueStarted()
    #   | SpeechFailed():                             return item.turn          # None = boot/shutdown cue
    #   SpeakerLevel() | Drained():                   return None               # device-level, not per turn
    #   _FrameIn() | _CommandIn() | _ShutdownIn() | SessionOpened():  return None
    #   case _: assert_never(item)
