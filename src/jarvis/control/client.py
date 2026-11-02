"""Control Socket client: used by ``jarvis ctl``, KDE Connect/hotkeys (via ``ctl``), the HUD and tests.

Knowledge owned here: connecting with a short timeout, request-id generation, reading
exactly one reply per request, the subscription handshake, and ``jarvis ctl`` exit codes
and one-line messages. "Daemon not running" is a value (``NoDaemon``), not an exception.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from jarvis.control.protocol import ErrorReply, EventMessage, Hello, OkReply, RequestBody, WireEvent


@dataclass(frozen=True)
class NoDaemon:
    socket_path: Path
    detail: str
    """E.g. "no socket", "connection refused", "timed out"."""


class EventFeed:
    """A live subscription: ``hello`` first, then events in ``seq`` order."""

    hello: Hello

    def __aiter__(self) -> AsyncIterator[EventMessage]:
        """Ends when the daemon closes the connection; ``overflowed`` tells why."""
        raise NotImplementedError

    @property
    def overflowed(self) -> bool:
        raise NotImplementedError

    async def collect_until(self, kind: type[WireEvent], *, timeout_s: float = 5.0) -> list[EventMessage]:
        """Test convenience: messages up to and including the first whose event is a ``kind``."""
        raise NotImplementedError


class ControlClient:
    def __init__(self, socket_path: Path, *, timeout_s: float = 1.0) -> None:
        self._socket_path = socket_path
        self._timeout_s = timeout_s

    async def request(self, body: RequestBody) -> OkReply | ErrorReply | NoDaemon:
        """One request on a fresh connection; ``timeout_s`` bounds connect *and* reply."""
        raise NotImplementedError

    def subscribe(self) -> AbstractAsyncContextManager[EventFeed]:
        """Open a subscription connection; ``__aenter__`` returns after ``hello``.
        Raises nothing on absence: use ``request`` first, or the HUD's reconnect loop."""
        raise NotImplementedError


async def run_ctl(argv: Sequence[str], *, socket_path: Path, out: TextIO, err: TextIO, timeout_s: float = 1.0) -> int:
    """``jarvis ctl <command> [arg...]``.

    0  ok (``status`` prints a compact human summary, ``--json`` prints the raw status)
    1  daemon not running / timed out   ("JARVIS is not running (no socket at ...)")
    2  usage error (unknown command, missing argument)
    3  rejected by the daemon           ("unavailable: Oracle is unavailable. ...")
    """
    raise NotImplementedError
    # match request_from_argv(argv, new_id()):
    #     ErrorReply(_, e) -> print usage line to err; return 2
    #     Request(_, body) -> match await ControlClient(socket_path, timeout_s=timeout_s).request(body): ...
