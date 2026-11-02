"""The Control Socket server (seam 2) and the single-instance lock.

Knowledge owned here: owner-only Unix socket lifecycle (0600, peer uid via
``SO_PEERCRED``, stale-socket cleanup under the lock, never TCP); per-connection framing
(line limit, decode errors answered and survived); dispatch of each request kind
(exhaustive ``match``); turning a core subscription into ``hello`` + ``event`` lines;
per-subscriber level-rate limiting; overflow notice + disconnect. It holds no turn state:
everything comes from the ``ControlTarget`` (the ``AssistantCore``).
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from types import TracebackType
from typing import Protocol, Self

from jarvis.core.bus import EventSubscription
from jarvis.core.vocabulary import Command, CommandResult, Status
from jarvis.settings import ControlSettings


class ControlTarget(Protocol):
    """What the server needs from the core (``AssistantCore`` satisfies it structurally)."""

    async def command(self, command: Command) -> CommandResult: ...

    def subscribe(self, *, capacity: int | None = ...) -> EventSubscription: ...

    def status(self) -> Status: ...


class DaemonAlreadyRunning(Exception):
    """Raised only by ``InstanceLock.acquire``; ``jarvis run`` prints it and exits 1."""

    def __init__(self, pid: int | None) -> None:
        super().__init__(f"JARVIS is already running (pid {pid}).")
        self.pid = pid


class InstanceLock:
    """One daemon per user session: ``flock`` on ``$XDG_RUNTIME_DIR/jarvis.lock`` + pidfile.

    Acquired by ``jarvis run`` *before* loading any model, so a second instance is refused
    in milliseconds. Holding the lock is what entitles a process to (re)create the socket,
    so ``ControlServer.serving`` takes the lock as an argument.
    """

    socket_path: Path

    @classmethod
    def acquire(cls, runtime_dir: Path, socket_name: str = "jarvis.sock") -> InstanceLock:
        raise NotImplementedError
        # fd = os.open(runtime_dir / "jarvis.lock", O_RDWR|O_CREAT|O_CLOEXEC, 0o600)
        # try fcntl.flock(fd, LOCK_EX|LOCK_NB) except BlockingIOError: raise DaemonAlreadyRunning(read pid)
        # write our pid; socket_path = runtime_dir / socket_name

    def release(self) -> None:
        raise NotImplementedError

    def __enter__(self) -> Self:
        return self

    def __exit__(self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None) -> None:
        self.release()


class ControlServer:
    @staticmethod
    @asynccontextmanager
    async def serving(target: ControlTarget, lock: InstanceLock, settings: ControlSettings) -> AsyncIterator[ControlServer]:
        """Bind ``lock.socket_path`` (unlink a stale file first; umask so the file is created
        0600 atomically, then chmod as belt and braces) and serve until exit, when every
        connection is closed and the socket file removed."""
        raise NotImplementedError
        yield  # pragma: no cover

    @property
    def socket_path(self) -> Path:
        raise NotImplementedError

    async def _connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        raise NotImplementedError
        # if peer uid (SO_PEERCRED) != os.getuid(): close
        # while line := await reader.readline() (limit settings.max_line_bytes; oversize -> bad_request, drain line):
        #     match decode_request(line):
        #         ErrorReply() as e:              write(e); continue           # never closes on bad input
        #         Request(id, SubscribeCmd()):    await self._stream(id, writer); return
        #         Request(id, StatusCmd()):       write(OkReply(id, status_to_wire(target.status())))
        #         Request(id, body):              write(reply_from_result(id, await target.command(command_from_wire(body))))
        #     (an unexpected exception -> ErrorReply(id, INTERNAL) and keep serving)

    async def _stream(self, request_id: str, writer: asyncio.StreamWriter) -> None:
        raise NotImplementedError
        # sub = target.subscribe(capacity=settings.subscriber_queue)
        # write(Hello(request_id, PROTOCOL_VERSION, status_to_wire(sub.snapshot)))
        # async for env in sub:
        #     wire = event_to_wire(env.event); if wire is None: continue
        #     if LevelEvent and sent one for this source < 1/level_max_hz ago (loop.time()): continue
        #     write(EventMessage(env.seq, wire)); await writer.drain()  -- a stalled peer only stalls this task
        # if sub.ended is OVERFLOW: write(Overflow(last_seq)); close
