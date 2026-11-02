"""Seam 1 (Assistant Core): turn scenarios. Every assertion is on the core's event stream
or on what a process-edge fake received. Runs on virtual time (see fakes.py)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jarvis.brain.port import BackendCapabilities, BackendKind, DenyCategory, RunShell, UseCustomTool
from jarvis.core.phrases import SAFETY_LINE
from jarvis.core.vocabulary import (
    Accepted,
    Activation,
    Answer,
    Ask,
    CaptureEnded,
    CuePlayed,
    CueEvent,
    LocalQuery,
    Rejected,
    RejectReason,
    Routed,
    SafetyRefused,
    SentenceSpoken,
    SessionStarted,
    Sleep,
    SleepChanged,
    Stop,
    SwitchPersona,
    Talk,
    Transcribed,
    TurnFinished,
    TurnOutcome,
    TurnStarted,
    WakeDetected,
)

from fakes import ScriptedBrain, core_harness, say, tool

pytestmark = pytest.mark.looptime  # virtual time: asyncio.sleep/loop.time advance only when idle


async def test_one_breath_command_needs_no_ack_and_strips_wake_phrase(tmp_path: Path) -> None:
    async with core_harness(tmp_path) as h:
        h.mic.feed(h.audio.silence(1.0), h.audio.wake(0.8, frames=2),
                   h.audio.speech("what time is it", 1.2), h.audio.silence(0.8))
        turn = await h.log.turn()

    assert turn.first(TurnStarted).activation is Activation.WAKE_WORD
    assert CueEvent.WAKE_ACK not in turn.cues()                      # speech began inside the ack window
    assert turn.first(Transcribed).raw == "hey jarvis what time is it"   # pre-roll reached the transcriber
    assert turn.first(Transcribed).text == "what time is it"
    assert turn.first(Routed).route == Answer(LocalQuery.TIME)
    assert turn.spoken() == ["It's 3:42 PM."]
    assert CueEvent.TASK_RECEIVED not in turn.cues()                 # bypass turns never get task_received
    assert turn.outcome is TurnOutcome.ANSWERED_LOCALLY


async def test_wake_needs_two_consecutive_frames_at_threshold(tmp_path: Path) -> None:
    async with core_harness(tmp_path) as h:
        h.mic.feed(h.audio.wake(0.9, frames=1), h.audio.silence(0.2),
                   h.audio.wake(0.64, frames=2), h.audio.silence(1.0))
        assert (await h.log.quiet(3.0)).all(WakeDetected) == []
        h.mic.feed(h.audio.wake(0.65, frames=2), h.audio.silence(6.0))
        assert (await h.log.next(WakeDetected)).score == pytest.approx(0.65)


@pytest.mark.parametrize(
    ("first_words", "voiced_s", "hears_please"),
    [
        ("open firefox", 0.56, True),          # < 1.0 s voiced: short tier (700 ms) survives a 560 ms pause
        ("open the thing I was editing and fix the failing test", 1.6, False),   # flowing tier (480 ms) ends it
    ],
)
async def test_endpoint_tier_follows_voiced_duration(
    tmp_path: Path, first_words: str, voiced_s: float, hears_please: bool
) -> None:
    async with core_harness(tmp_path) as h:
        h.mic.feed(h.audio.wake(0.9), h.audio.speech(first_words, voiced_s), h.audio.silence(0.56),
                   h.audio.speech("please", 0.24), h.audio.silence(1.0))
        turn = await h.log.turn()
    assert turn.first(Transcribed).text.endswith("please") is hears_please


async def test_pause_after_wake_plays_ack_and_gated_time_is_not_silence(tmp_path: Path) -> None:
    async with core_harness(tmp_path) as h:
        h.mic.feed(h.audio.wake(0.9), h.audio.silence(0.4),           # nothing inside the ack window
                   h.audio.silence(4.9),                               # cue (0.6 s) + hangover are gated:
                   h.audio.speech("open firefox", 0.56), h.audio.silence(0.8))   # ...so 5 s timeout not reached
        turn = await h.log.turn()
    assert turn.cues()[0] is CueEvent.WAKE_ACK
    assert turn.first(Transcribed).text == "open firefox"


async def test_wake_then_silence_returns_to_idle_quietly(tmp_path: Path) -> None:
    async with core_harness(tmp_path) as h:
        h.mic.feed(h.audio.wake(0.9), h.audio.silence(6.0))
        turn = await h.log.turn()
    assert turn.outcome is TurnOutcome.NO_SPEECH
    assert turn.spoken() == [] and turn.cues() == [CueEvent.WAKE_ACK]


async def test_safety_deny_mid_turn(tmp_path: Path) -> None:
    brain = ScriptedBrain([[
        say("Right away. Clearing the system logs now, master. "),
        tool(RunShell("sudo rm -rf /var/log/journal")),
        say("All done, the logs are gone. "),                          # must never be heard
    ]])
    async with core_harness(tmp_path, brain=brain) as h:
        h.mic.feed(h.audio.silence(1.0), h.audio.wake(0.8, frames=2),
                   h.audio.speech("clear the system logs", 1.2), h.audio.silence(0.8))
        turn = await h.log.turn()

    assert turn.first(Transcribed).text == "clear the system logs"
    assert brain.sent[-1] == (1, "clear the system logs")
    refused = turn.first(SafetyRefused)
    assert refused.category is DenyCategory.PRIVILEGE_ESCALATION
    after = turn.after(SafetyRefused)
    assert after.cues() == [CueEvent.SAFETY_BLOCKED]
    assert after.spoken() == ["That would be… unwise.", SAFETY_LINE]   # fallback line (no clip), then ADR 06 line
    assert all("logs are gone" not in s for s in turn.spoken())        # remainder discarded
    assert turn.outcome is TurnOutcome.REFUSED
    assert h.audit.entries[-1].call.action == RunShell("sudo rm -rf /var/log/journal")


async def test_stop_while_speaking_drains_a_non_interruptible_session(tmp_path: Path) -> None:
    brain = ScriptedBrain([
        [say("First sentence of a rather long answer. "), say("Second sentence that keeps on going. "),
         say("Third sentence that nobody should hear. ")],
        [say("A fresh answer for a fresh question.")],
    ], interruptible=False)
    async with core_harness(tmp_path, brain=brain) as h:
        assert await h.core.command(Ask("tell me a long story")) == Accepted()
        await h.log.next(SentenceSpoken)
        assert await h.core.command(Stop()) == Accepted()
        assert (await h.log.next(TurnFinished)).outcome is TurnOutcome.INTERRUPTED
        assert (await h.log.quiet(3.0)).all(SentenceSpoken) == []      # flushed; stale deltas discarded
        assert brain.interrupts == 0                                    # drain-and-discard path

        await h.core.command(Ask("and now?"))
        second = await h.log.turn()
    assert second.spoken() == ["A fresh answer for a fresh question."]
    assert brain.sent[-1] == (1, "and now?")                            # same session, kept alive


async def test_talk_while_speaking_barges_in(tmp_path: Path) -> None:
    brain = ScriptedBrain([[say("This answer is long enough to interrupt politely. "), say("And it goes on and on.")]])
    async with core_harness(tmp_path, brain=brain) as h:
        await h.core.command(Ask("ramble"))
        await h.log.next(SentenceSpoken)
        await h.core.command(Talk())
        assert (await h.log.next(TurnFinished)).outcome is TurnOutcome.INTERRUPTED
        assert (await h.log.next(TurnStarted)).activation is Activation.PUSH_TO_TALK
    assert brain.interrupts == 1                                        # native interrupt used


async def test_sleep_closes_the_mic_and_talk_is_refused(tmp_path: Path) -> None:
    async with core_harness(tmp_path) as h:
        await h.core.command(Sleep())
        assert (await h.log.next(SleepChanged)).asleep is True
        h.mic.feed(h.audio.wake(0.99, frames=4))
        assert (await h.log.quiet(2.0)).all(WakeDetected) == []
        assert not h.mic.is_open and h.mic.pending == 4                  # asleep consumed no frames
        refused = await h.core.command(Talk())
        assert isinstance(refused, Rejected) and refused.reason is RejectReason.ASLEEP


async def test_fact_saved_through_a_tool_is_in_the_next_sessions_preamble(tmp_path: Path) -> None:
    brain = ScriptedBrain([[
        tool(UseCustomTool("save_memory"), type="fact", key="paths.trade", value="/mnt/data_drive/trade"),
        say("Noted, master. I shall remember where it lives."),
    ]])
    async with core_harness(tmp_path, brain=brain) as h:
        await h.core.command(Ask("remember that my trading project is at /mnt/data_drive/trade"))
        turn = await h.log.turn()
        assert turn.outcome is TurnOutcome.ANSWERED                     # memory tools are not "acting"
        assert CueEvent.TASK_COMPLETED not in turn.cues()

        assert await h.core.command(SwitchPersona("architect")) == Accepted()
        await h.log.next(SessionStarted)
    assert "paths.trade: /mnt/data_drive/trade" in brain.specs[-1].system_prompt
    assert "paths.trade" not in brain.specs[0].system_prompt            # Jarvis's session predates the fact
    assert (await h.store.search("where's my \"trading\" project? AND *", limit=5))[0].key == "paths.trade"


async def test_boot_cue_follows_readiness(tmp_path: Path) -> None:
    async with core_harness(tmp_path) as h:
        first_cue = await h.log.next(CuePlayed)
        assert first_cue.cue is CueEvent.BOOT
        assert h.mic.is_open and h.brain.specs                          # wake listening live, Jarvis warm


async def test_ungated_backend_is_opened_without_tools(tmp_path: Path) -> None:
    """Synthesis graft: capabilities are enforced by the core, not trusted to the adapter."""
    oracle = ScriptedBrain([[say("The documentation says version three, master.")]],
                           kind=BackendKind.ANTIGRAVITY,
                           caps=BackendCapabilities(gates_tools=False, custom_tools=False))
    async with core_harness(tmp_path, oracle=oracle) as h:
        assert await h.core.command(SwitchPersona("oracle")) == Accepted()
        await h.core.command(Ask("what version is the latest release"))
        await h.log.turn()
    spec = oracle.specs[-1]
    assert spec.builtins == frozenset()                                 # no shell for an ungated backend
    assert spec.tools == ()                                             # no custom tools either
    assert "paths." in spec.system_prompt or spec.system_prompt          # preamble still composed
