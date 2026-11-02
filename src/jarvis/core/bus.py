"""The ordered domain-event stream and its subscriptions.

Knowledge owned here: sequencing (one global ``seq``), fan-out to many subscribers,
back-pressure (bounded queues; level meters coalesced latest-wins so they can never
fill a queue; overflow ends the subscription), and the gap-free snapshot handshake.

Only ``AssistantCore``'s actor task publishes. Subscribers are the Control Socket
server (one subscription per socket subscriber), the journal writer, and tests.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from enum import StrEnum

from jarvis.core.vocabulary import DomainEvent, Status


@dataclass(frozen=True)
class Envelope:
    seq: int
    """Strictly increasing across the daemon's lifetime; identical for every subscriber."""
    at: float
    """Clock.monotonic() when published."""
    event: DomainEvent


class SubscriptionEnd(StrEnum):
    CLOSED = "closed"
    """The subscriber called ``close()``."""
    OVERFLOW = "overflow"
    """The subscriber fell more than ``capacity`` non-level events behind."""
    SHUTDOWN = "shutdown"
    """The core stopped; the last envelope was the final ``StateChanged``/cue of shutdown."""


class EventSubscription:
    """An async iterator of envelopes starting right after ``snapshot`` (no gap, no overlap).

    ``Level`` events are held in one slot per ``LevelSource`` and delivered latest-wins
    between queued events, so they are dropped first under pressure. When more than
    ``capacity`` other events are pending the subscription ends with ``OVERFLOW``.
    ``capacity=None`` means unbounded (internal lossless consumers such as the journal).
    """

    snapshot: Status

    def __init__(self, snapshot: Status, capacity: int | None, on_close: Callable[[EventSubscription], None]) -> None:
        self.snapshot = snapshot
        raise NotImplementedError

    def __aiter__(self) -> AsyncIterator[Envelope]:
        raise NotImplementedError
        # while True:
        #   if ended and queue empty: return
        #   wait for queue item or level slot
        #   yield queued items first (in seq order), then any coalesced level with seq > last yielded

    @property
    def ended(self) -> SubscriptionEnd | None:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def _offer(self, envelope: Envelope) -> None:
        """Called by ``EventBus.publish`` (same loop, never blocks)."""
        raise NotImplementedError


class EventBus:
    """Core-internal publisher. Not exported from ``jarvis.core``."""

    def __init__(self, monotonic: Callable[[], float]) -> None:
        raise NotImplementedError

    def publish(self, event: DomainEvent) -> Envelope:
        raise NotImplementedError  # seq += 1; env = Envelope(seq, monotonic(), event); for s in subs: s._offer(env)

    def subscribe(self, snapshot: Status, capacity: int | None) -> EventSubscription:
        raise NotImplementedError

    def end_all(self, reason: SubscriptionEnd) -> None:
        raise NotImplementedError
