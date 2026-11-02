"""Every sentence JARVIS composes itself (not the Brain, not a cue fallback line).

One module so wording is tuned in one place and adapters never phrase anything:
adapters return enums (``ActionFailure``, ``BrainErrorKind``), this module turns them
into speech.
"""

from __future__ import annotations

from datetime import datetime
from typing import Final

from jarvis.brain.port import BrainError
from jarvis.core.vocabulary import ActionFailure, LocalQuery, Persona

SAFETY_LINE: Final = "This action requires elevated permissions. Please run it manually in a terminal."
"""ADR 06, verbatim."""

CONTEXT_LOST: Final = "My apologies. I lost the thread of our earlier conversation."


def brain_error(error: BrainError, persona: Persona) -> str:
    raise NotImplementedError
    # AUTH        -> "I can't reach Claude: Claude Code is logged out. Please run claude and log in."
    # USAGE_LIMIT -> "We've hit the subscription usage limit[, it resets at 5 PM]."
    # UNAVAILABLE -> f"{persona.display_name} is unavailable right now."
    # CRASHED     -> "My thinking process crashed. I'll restart it on your next request."
    # TIMEOUT     -> "That took too long, so I stopped waiting."


def action_failed(failure: ActionFailure) -> str:
    raise NotImplementedError
    # NO_MEDIA_PLAYER -> "No media player is running."   etc. (one short sentence each)


def local_answer(query: LocalQuery, now: datetime) -> str:
    raise NotImplementedError  # TIME -> "It's 3:42 PM."   DATE -> "It's Monday, the 2nd of November."


def persona_switched(persona: Persona) -> str:
    raise NotImplementedError  # f"{persona.display_name} at your service."


def persona_unavailable(persona: Persona, reason: str) -> str:
    raise NotImplementedError  # f"{persona.display_name} is unavailable. {reason}"


def internal_error() -> str:
    return "Something went wrong on my side. Please try again."
