"""Antigravity backend (Oracle: Gemini Flash under the user's Google subscription).

The only module that knows how Antigravity is reached. Its headless/programmatic
streaming surface is unconfirmed (spec risk; ticket 9), so this adapter is shaped to the
port and degrades to ``Unavailable`` until that surface is pinned down:

* ``probe()``  resolves ``settings.command`` and performs a handshake (version + a
  capability query for headless streaming). Any failure -> ``Unavailable`` with a
  speakable reason and a ``doctor`` fix. Never raises.
* ``open()``   spawns the transport (it inherits the daemon's ``no_new_privs`` and scrubbed
  environment, see ``jarvis.daemon.harden_process``) and sends ``spec.system_prompt``.
* ``capabilities`` is ``gates_tools=False, custom_tools=False`` until ticket 9 confirms the
  transport can route every tool call through ``spec.gate`` and host custom tools. Until
  then ``Personas`` opens Oracle with no built-ins and no custom tools (memory preamble
  only): fewer tools, never ungated ones. Flipping a flag here is the whole change.
* ``interruptible`` is False until a native cancel is confirmed: the core then uses its
  drain-and-discard path and the session stays alive.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from jarvis.brain.port import (
    Availability,
    BackendCapabilities,
    BackendKind,
    BrainError,
    BrainEvent,
    BrainSession,
    SessionSpec,
)
from jarvis.settings import AntigravitySettings


class AntigravityBackend:
    def __init__(self, settings: AntigravitySettings) -> None:
        self._settings = settings

    @property
    def kind(self) -> BackendKind:
        return BackendKind.ANTIGRAVITY

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(gates_tools=False, custom_tools=False)  # until ticket 9

    async def probe(self) -> Availability:
        raise NotImplementedError
        # if not shutil.which(settings.command): Unavailable("Antigravity is not installed.", fix=...)
        # handshake fails / no headless streaming: Unavailable("Antigravity has no headless mode I can use.", fix=...)

    async def open(self, spec: SessionSpec) -> BrainSession | BrainError:
        raise NotImplementedError


class _AntigravitySession:
    @property
    def interruptible(self) -> bool:
        return False

    def send(self, text: str) -> AsyncIterator[BrainEvent]:
        raise NotImplementedError
        # write request line; for each streamed line: text -> TextDelta, tool request -> await spec.gate(...)
        # then run/skip; tool result -> ToolFinished; end -> TurnEnded(False); EOF/exit -> BrainFailed(CRASHED)

    async def interrupt(self) -> None:
        raise NotImplementedError  # not supported: never called while interruptible is False

    async def close(self) -> None:
        raise NotImplementedError
