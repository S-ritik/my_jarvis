"""Memory as the Brain sees it: the ``BrainContext`` given to every new session.

Knowledge owned here: the two tool contracts (names, descriptions, JSON Schemas, argument
validation, result wording for the model) and how big the session preamble may be.
The store's internals stay in ``store.py``; the core never sees either beyond the
``BrainContext`` protocol (``preamble()`` + ``tools()``).

Tools (identical for every persona whose backend supports custom tools):

* ``save_memory(type, key, value)``  type in {"fact", "snippet"}; for a snippet ``key`` is
  an optional title. Facts upsert by normalized key.
* ``search_memory(query)``           top ``search_limit`` hits, one per line:
  ``fact paths.trade: /mnt/data_drive/trade``.
"""

from __future__ import annotations

from typing import Final

from jarvis.brain.port import BrainTool, JsonObject, ToolOutput
from jarvis.memory.store import MemoryStore
from jarvis.settings import MemorySettings

SAVE_SCHEMA: Final[JsonObject] = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["fact", "snippet"]},
        "key": {"type": "string", "description": "Namespaced fact key like 'paths.trade', or a snippet title (may be empty)."},
        "value": {"type": "string", "description": "The fact value or the snippet body."},
    },
    "required": ["type", "key", "value"],
    "additionalProperties": False,
}

SEARCH_SCHEMA: Final[JsonObject] = {
    "type": "object",
    "properties": {"query": {"type": "string", "description": "Plain keywords; punctuation is ignored."}},
    "required": ["query"],
    "additionalProperties": False,
}


class MemoryContext:
    """Implements ``jarvis.core.ports.BrainContext`` over a ``MemoryStore``."""

    def __init__(self, store: MemoryStore, settings: MemorySettings) -> None:
        self._store = store
        self._settings = settings

    async def preamble(self) -> str:
        return await self._store.preamble(max_chars=self._settings.preamble_chars)

    def tools(self) -> tuple[BrainTool, ...]:
        return (
            BrainTool("save_memory", "Permanently remember a fact (replaces the old value for the same key) or a note.",
                      SAVE_SCHEMA, self._save),
            BrainTool("search_memory", "Search remembered facts and notes by keywords.", SEARCH_SCHEMA, self._search),
        )

    async def _save(self, args: JsonObject) -> ToolOutput:
        raise NotImplementedError
        # validate args against SAVE_SCHEMA by hand (str fields, enum) -> ToolOutput(problem, failed=True)
        # item = Fact(key, value) if type == "fact" else Snippet(key or None, value)
        # match await store.save(item):
        #   Saved(FACT, key, replaced) -> ToolOutput(f"{'Updated' if replaced else 'Saved'} fact {key}.", False)
        #   Saved(SNIPPET, title, _)   -> ToolOutput("Saved note.", False)
        #   SaveRejected(reason)       -> ToolOutput(reason, failed=True)

    async def _search(self, args: JsonObject) -> ToolOutput:
        raise NotImplementedError
        # hits = await store.search(query, limit=settings.search_limit)
        # ToolOutput("\n".join(f"{h.kind} {h.key}: {h.value}" for h in hits) or "No memories match.", False)
