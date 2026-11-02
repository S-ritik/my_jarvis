"""The HUD's client contract (``jarvis hud``). Rendering internals are out of scope.

The HUD is a pure subscriber: it imports ``jarvis.control.protocol`` and
``jarvis.control.client`` only (never ``jarvis.core``), folds wire messages into an
immutable ``HudView`` with a pure reducer, and sends commands over short-lived command
connections. The daemon never depends on it; it reconnects forever.

The Qt side runs ``watch`` on a worker thread's event loop and marshals each ``HudView``
to the GUI thread with a queued signal; the renderer is a function of the latest view
plus its own animation clock (rings, ripples, breathing).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Final

from jarvis.control.protocol import (
    RequestBody,
    ServerMessage,
    StopCmd,
    TalkCmd,
    ToggleSleepCmd,
    WireState,
)


class Link(StrEnum):
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    """Shown as a dim static ring while retrying."""


@dataclass(frozen=True)
class HudView:
    link: Link
    state: WireState
    asleep: bool
    persona: str
    mic_level: float
    speaker_level: float


INITIAL_VIEW: Final = HudView(Link.CONNECTING, WireState.IDLE, False, "", 0.0, 0.0)

CLICK: Final[RequestBody] = TalkCmd()
MENU: Final[tuple[tuple[str, RequestBody], ...]] = (
    ("Stop", StopCmd()),
    ("Sleep / wake", ToggleSleepCmd()),
)
"""Click-through toggle is local (Qt settings); persona entries come from the hello status."""


def apply(view: HudView, message: ServerMessage) -> HudView:
    """Pure reducer: Hello resets everything from its status; StateEvent/SleepEvent/
    PersonaEvent/LevelEvent update fields; replies, UnknownEvent and other events are ignored."""
    raise NotImplementedError


async def watch(socket_path: Path, *, retry_s: float = 1.0) -> AsyncIterator[HudView]:
    """Yield a new view on every change, forever: subscribe, fold, and on disconnect yield
    ``Link.DISCONNECTED`` and retry every ``retry_s`` (daemon restarts are invisible)."""
    raise NotImplementedError
    yield INITIAL_VIEW  # pragma: no cover


async def send(socket_path: Path, body: RequestBody) -> bool:
    """Fire one command (click, menu); False if the daemon is absent or rejected it."""
    raise NotImplementedError
