"""System prompt composition (five parts, spec "System prompt").

Knowledge owned here: the voice rules, the safety rules, the tool guidance (no timers in
v1), and the order in which the five parts are assembled. The persona supplies its
Tier-2 flavor; the ``BrainContext`` supplies the memory preamble text (already formatted
and size-capped by the Memory Store; this module does not know what a fact is).
"""

from __future__ import annotations

from typing import Final

from jarvis.core.vocabulary import Persona

VOICE_RULES: Final = (
    "You are speaking aloud through a speaker. Answer in one to three short sentences. "
    "Never use markdown, lists, headings or emoji. Never read code, commands or URLs aloud; "
    "offer to write long content to a file instead."
)
SAFETY_RULES: Final = (
    "Never attempt privileged or system-level actions (sudo, su, disk tools, system directories). "
    "If a tool call is refused, do not retry it and do not work around it."
)
TOOL_GUIDANCE: Final = (
    "You cannot set timers, alarms or reminders yet; say so plainly instead of improvising "
    "(for example with sleep or notify-send). Use save_memory for durable facts the user asks "
    "you to remember, and search_memory before saying you don't know something about them."
)


def compose_system_prompt(persona: Persona, memory_preamble: str) -> str:
    raise NotImplementedError
    # "\n\n".join(p for p in (VOICE_RULES, persona.flavor, SAFETY_RULES, memory_preamble, TOOL_GUIDANCE) if p)
