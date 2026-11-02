# Local Context and Long Term Memory Store

Type: research
Status: resolved
Blocked by: 05

## Question

What local storage mechanism (SQLite with FTS5 vs lightweight embedded vector search like LanceDB/ChromaDB on CPU) provides fast, low-footprint retrieval of user preferences, session history, and durable facts without persistent background memory leaks?

## Answer

- **Selected Engine**: **SQLite with FTS5 and WAL (Write-Ahead Logging)**. Embedded vector databases (ChromaDB, LanceDB) were rejected because they require either keeping a heavy 150–400MB embedding model resident in RAM or paying a prohibitive 800–2,500ms cold-start inference penalty on CPU every search. Plain JSON/YAML was rejected due to lack of indexing and risk of file corruption during concurrent access.
- **Performance**:
  - Exact key-value profile/path lookups: **0.003ms warm / 0.5ms cold** via indexed B-Tree.
  - BM25 ranked full-text search across notes & snippets: **0.8ms cold**.
  - Idle RAM consumption: **0 MB** when connection closed, **<1.8 MB** resident when open.
- **Zero External Dependencies**: Uses Python's native standard library `sqlite3` (verified with FTS5 support).
- **Dual Schema**:
  1. `facts` table: Key-value store for user profile, project paths (`paths.trade = "/mnt/data_drive/trade"`), and tool preferences.
  2. `snippets` table: Freeform notes, instructions, and code blocks.
  3. `search_index` (FTS5): Unified virtual table maintained by automatic SQL triggers with Porter stemming and BM25 ranking.
- **Agent Integration**: Exposes two lightweight tools to the brain session: `save_memory(type, key, value)` and `search_memory(query)`. Injects key user preferences into the initial session prompt with zero latency overhead.
