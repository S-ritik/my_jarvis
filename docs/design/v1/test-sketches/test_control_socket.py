"""Seam 2 (Control Socket): the real server on a temp path, in front of a core wired with the
same fakes, driven by the real ``jarvis ctl`` code (``run_ctl``) and raw subscribers."""

from __future__ import annotations

import asyncio
import io
import json
import stat
from collections.abc import Sequence
from pathlib import Path

import pytest

from jarvis.control.client import ControlClient, run_ctl
from jarvis.control.protocol import (
    PROTOCOL_VERSION,
    CueWireEvent,
    ErrorCode,
    ErrorReply,
    OkReply,
    PersonaEvent,
    SentenceEvent,
    SleepEvent,
    StateEvent,
    StatusCmd,
    TranscriptEvent,
    TurnEndedEvent,
    TurnStartedEvent,
    WireEvent,
    WireState,
    decode_server,
)
from jarvis.control.server import DaemonAlreadyRunning, InstanceLock

from fakes import ScriptedBrain, say, socket_harness

pytestmark = pytest.mark.looptime


def kinds(events: Sequence[WireEvent]) -> list[type]:
    return [type(e) for e in events]


async def ctl(path: Path, *argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = await run_ctl(list(argv), socket_path=path, out=out, err=err)
    return code, out.getvalue(), err.getvalue()


async def test_ask_turn_observed_end_to_end(tmp_path: Path) -> None:
    brain = ScriptedBrain([[say("A fine evening, master. Nothing needs your attention.")]])
    async with socket_harness(tmp_path, brain=brain) as s:
        async with ControlClient(s.socket_path).subscribe() as feed:
            assert feed.hello.protocol == PROTOCOL_VERSION
            assert feed.hello.status.state is WireState.IDLE and feed.hello.status.persona == "jarvis"
            code, _, _ = await ctl(s.socket_path, "ask", "anything", "new?")
            assert code == 0
            events = [m.event for m in await feed.collect_until(TurnEndedEvent)]

    turn_events = [e for e in events if not isinstance(e, (SleepEvent, PersonaEvent))]
    assert kinds(turn_events) == [TurnStartedEvent, StateEvent, TranscriptEvent, CueWireEvent,
                                  StateEvent, SentenceEvent, SentenceEvent, TurnEndedEvent]
    assert [e.text for e in turn_events if isinstance(e, SentenceEvent)] == [
        "A fine evening, master.", "Nothing needs your attention."]


@pytest.mark.parametrize(
    ("argv", "code", "expect"),
    [
        (["talk"], 0, StateEvent(WireState.LISTENING)),
        (["sleep"], 0, SleepEvent(True)),
        (["mute"], 0, SleepEvent(True)),
        (["toggle-sleep"], 0, SleepEvent(True)),
        (["persona", "architect"], 0, PersonaEvent("architect", "Architect")),
        (["persona", "oracle"], 3, None),          # unavailable: refused out loud, non-zero exit
        (["persona", "banana"], 3, None),
        (["stop"], 0, None),
        (["status"], 0, None),
        (["dance"], 2, None),                      # usage error before any I/O
    ],
)
async def test_command_replies_and_effects(tmp_path: Path, argv: list[str], code: int, expect: WireEvent | None) -> None:
    async with socket_harness(tmp_path) as s:
        async with ControlClient(s.socket_path).subscribe() as feed:
            got, out, err = await ctl(s.socket_path, *argv)
            assert got == code
            assert (err.count("\n") <= 1) and (code == 0 or err)
            if expect is not None:
                assert expect in [m.event for m in await feed.collect_until(type(expect))]


async def test_many_subscribers_see_the_same_sequence(tmp_path: Path) -> None:
    async with socket_harness(tmp_path, brain=ScriptedBrain([[say("Yes, master, consider it done.")]])) as s:
        client = ControlClient(s.socket_path)
        async with client.subscribe() as a, client.subscribe() as b, client.subscribe() as c:
            await ctl(s.socket_path, "ask", "hello")
            seqs = [[m.seq for m in await f.collect_until(TurnEndedEvent)] for f in (a, b, c)]
    assert seqs[0] == seqs[1] == seqs[2] == sorted(seqs[0])


async def test_malformed_and_unknown_lines_are_answered_and_serving_continues(tmp_path: Path) -> None:
    async with socket_harness(tmp_path) as s:
        reader, writer = await asyncio.open_unix_connection(s.socket_path)
        for line in (b"not json\n", b"[1,2]\n", b'{"cmd":"talk"}\n', b'{"id":"1","cmd":"fly"}\n',
                     b'{"id":"2","cmd":"persona"}\n', b"x" * 70_000 + b"\n"):
            writer.write(line)
            await writer.drain()
            reply = decode_server(await reader.readline())
            assert isinstance(reply, ErrorReply)
            assert reply.error.code in (ErrorCode.BAD_REQUEST, ErrorCode.UNKNOWN_COMMAND)
        writer.write(json.dumps({"id": "3", "cmd": "status"}).encode() + b"\n")
        await writer.drain()
        assert json.loads(await reader.readline())["ok"] is True
        writer.close()
        assert isinstance(await ControlClient(s.socket_path).request(StatusCmd()), OkReply)


async def test_socket_is_owner_only(tmp_path: Path) -> None:
    async with socket_harness(tmp_path) as s:
        assert stat.S_IMODE(s.socket_path.stat().st_mode) == 0o600


async def test_ctl_without_daemon_fails_fast(tmp_path: Path) -> None:
    async with asyncio.timeout(1.5):
        code, _, err = await ctl(tmp_path / "absent.sock", "talk")
    assert code == 1 and err.count("\n") == 1 and "not running" in err


async def test_ctl_against_a_hung_daemon_times_out(tmp_path: Path) -> None:
    path = tmp_path / "hung.sock"
    server = await asyncio.start_unix_server(lambda r, w: None, path=str(path))   # accepts, never replies
    async with server, asyncio.timeout(1.5):
        code, _, err = await ctl(path, "status")
    assert code == 1 and "timed out" in err


async def test_second_instance_is_refused(tmp_path: Path) -> None:
    async with socket_harness(tmp_path) as s:
        with pytest.raises(DaemonAlreadyRunning):
            InstanceLock.acquire(s.socket_path.parent)
