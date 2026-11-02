"""Tier-1 lifecycle cue selection (ADR 09).

Knowledge owned here: per-event enabled flag, clip pool, fallback line; preloading every
clip once at boot (so playback starts in < 10 ms); uniform random choice within a pool
with no immediate repeat, from an injected ``Random``; fallback to the line when the pool
is empty or every clip failed to decode.

*When* each cue plays is turn policy and lives in ``AssistantCore`` (one table there).
*How* a choice becomes sound is ``Speech``'s job (clip enqueued vs. line synthesized).
"""

from __future__ import annotations

from dataclasses import dataclass
from random import Random
from typing import TypeAlias

from jarvis.audio import PcmClip
from jarvis.core.ports import ClipLoader
from jarvis.core.vocabulary import CueEvent
from jarvis.settings import CueSettings


@dataclass(frozen=True, eq=False)
class PlayClip:
    name: str
    clip: PcmClip


@dataclass(frozen=True)
class SpeakLine:
    text: str


@dataclass(frozen=True)
class Silent:
    """The event is disabled in config."""


CueChoice: TypeAlias = PlayClip | SpeakLine | Silent


class CueBoard:
    @classmethod
    async def load(cls, settings: CueSettings, loader: ClipLoader, rng: Random) -> CueBoard:
        """Decode every pool clip once. Clips that fail to load are logged and left out of
        their pool (an emptied pool falls back to the line)."""
        raise NotImplementedError

    def pick(self, cue: CueEvent) -> CueChoice:
        raise NotImplementedError
        # spec = settings.events[cue]
        # if not spec.enabled: return Silent()
        # pool = loaded[cue]
        # if not pool: return SpeakLine(spec.fallback_line)
        # candidates = [c for c in pool if c.name != last[cue]] or pool
        # choice = rng.choice(candidates); last[cue] = choice.name; return choice
