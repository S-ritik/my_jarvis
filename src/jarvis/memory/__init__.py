"""The Memory Store (indexer) and its Brain-facing context.

- ``jarvis.memory.store.MemoryStore``    SQLite/FTS5: open, save (upsert), search (sanitized BM25), preamble
- ``jarvis.memory.tools.MemoryContext``  ``BrainContext``: session preamble + save_memory/search_memory
"""
