"""The Memory Store (ADR 08): one SQLite file, WAL, FTS5 (porter), BM25.

The only module that imports ``sqlite3`` or spells a table/column name. Callers see
``Fact``/``Snippet`` in, ``MemoryHit``/preamble text out.

Knowledge owned here: schema + migrations; fact-key normalization; upsert-by-key;
the trigger-maintained ``search_index``; free-text -> safe FTS5 query sanitization;
BM25 column weights and tie-breaks; preamble ordering and size cap. Connections are
opened per operation (idle cost zero) on a worker thread; every public method is async.

Schema (applied by ``open``; ``PRAGMA user_version`` = 1)::

    PRAGMA journal_mode = WAL;           -- once; persistent for the file
    PRAGMA foreign_keys = ON;

    CREATE TABLE IF NOT EXISTS facts (
        id          INTEGER PRIMARY KEY,
        key         TEXT    NOT NULL UNIQUE,        -- normalized 'namespace.name', e.g. 'paths.trade'
        value       TEXT    NOT NULL,
        revision    INTEGER NOT NULL,               -- global write counter: deterministic recency order
        updated_at  TEXT    NOT NULL                -- ISO-8601 UTC, for humans inspecting the file
    );
    CREATE TABLE IF NOT EXISTS snippets (
        id          INTEGER PRIMARY KEY,
        title       TEXT,                           -- optional title/key
        body        TEXT    NOT NULL,
        created_at  TEXT    NOT NULL
    );
    -- One contentful FTS5 table over both sources. rowid encodes the source so triggers
    -- update by rowid (O(log n)) instead of scanning UNINDEXED columns:
    --   fact id n -> rowid 2n ; snippet id n -> rowid 2n+1
    CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(
        kind  UNINDEXED,                            -- 'fact' | 'snippet'
        key,                                        -- fact key ('.' and '_' tokenize as separators) or snippet title
        body,                                       -- fact value or snippet body
        tokenize = 'porter unicode61'
    );
    CREATE TRIGGER IF NOT EXISTS facts_ai AFTER INSERT ON facts BEGIN
        INSERT INTO search_index(rowid, kind, key, body) VALUES (2*new.id, 'fact', new.key, new.value);
    END;
    CREATE TRIGGER IF NOT EXISTS facts_au AFTER UPDATE ON facts BEGIN
        DELETE FROM search_index WHERE rowid = 2*old.id;
        INSERT INTO search_index(rowid, kind, key, body) VALUES (2*new.id, 'fact', new.key, new.value);
    END;
    CREATE TRIGGER IF NOT EXISTS facts_ad AFTER DELETE ON facts BEGIN
        DELETE FROM search_index WHERE rowid = 2*old.id;
    END;
    CREATE TRIGGER IF NOT EXISTS snippets_ai AFTER INSERT ON snippets BEGIN
        INSERT INTO search_index(rowid, kind, key, body) VALUES (2*new.id+1, 'snippet', coalesce(new.title, ''), new.body);
    END;
    CREATE TRIGGER IF NOT EXISTS snippets_ad AFTER DELETE ON snippets BEGIN
        DELETE FROM search_index WHERE rowid = 2*old.id+1;
    END;
    -- (snippets are append-only in v1; an _au trigger mirrors facts_au if editing is ever added)

Upsert::

    INSERT INTO facts(key, value, revision, updated_at)
    VALUES (:key, :value, (SELECT coalesce(max(revision), 0) + 1 FROM facts), :now)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                   revision = excluded.revision,
                                   updated_at = excluded.updated_at;

Search (``:q`` from ``_fts_query``; weights per column: kind=0, key=2.0, body=1.0)::

    SELECT kind, key, body, bm25(search_index, 0.0, 2.0, 1.0) AS rank
    FROM search_index WHERE search_index MATCH :q
    ORDER BY rank, rowid DESC LIMIT :limit;

Preamble::

    SELECT key, value FROM facts ORDER BY revision DESC;   -- accumulate until max_chars
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, TypeAlias

SCHEMA_VERSION: Final = 1
BM25_WEIGHTS: Final = (0.0, 2.0, 1.0)
"""(kind, key, body). The one knob for "change FTS ranking"."""
STOPWORDS: Final = frozenset({"a", "an", "the", "my", "is", "are", "where", "what", "s", "of", "to", "in", "and", "or", "not", "near"})


class MemoryKind(StrEnum):
    FACT = "fact"
    SNIPPET = "snippet"


@dataclass(frozen=True)
class Fact:
    key: str
    """Raw key as given; normalized by the store (see ``normalize_key``)."""
    value: str


@dataclass(frozen=True)
class Snippet:
    title: str | None
    body: str


MemoryItem: TypeAlias = Fact | Snippet


@dataclass(frozen=True)
class Saved:
    kind: MemoryKind
    key: str
    """Normalized fact key, or the snippet title ('' when untitled)."""
    replaced: bool
    """True when an existing fact's value was replaced (upsert)."""


@dataclass(frozen=True)
class SaveRejected:
    reason: str
    """E.g. "key must contain letters". Returned to the Brain as the tool's error text."""


SaveResult: TypeAlias = Saved | SaveRejected


@dataclass(frozen=True)
class MemoryHit:
    kind: MemoryKind
    key: str
    value: str


class MemoryUnavailable(Exception):
    """Raised only by ``MemoryStore.open`` (boot fails loudly): FTS5 missing, file unwritable,
    newer schema version than this build understands."""


class MemoryStore:
    @classmethod
    async def open(cls, path: Path, *, now: Callable[[], datetime]) -> MemoryStore:
        """Create the parent dir, apply schema/migrations, enable WAL, verify FTS5
        (``CREATE VIRTUAL TABLE temp.probe USING fts5(x)``). ``now`` stamps ``updated_at``
        / ``created_at`` only; ordering never depends on it."""
        raise NotImplementedError

    async def save(self, item: MemoryItem) -> SaveResult:
        raise NotImplementedError
        # Fact: key = normalize_key(item.key) or SaveRejected; value stripped, non-empty else SaveRejected
        #       existed = SELECT 1 FROM facts WHERE key = ?; run upsert; Saved(FACT, key, replaced=existed)
        # Snippet: body non-empty else SaveRejected; INSERT INTO snippets(...); Saved(SNIPPET, title or '', False)

    async def search(self, query: str, *, limit: int) -> tuple[MemoryHit, ...]:
        """Never raises on user text: punctuation, quotes and FTS operators are neutralized."""
        raise NotImplementedError
        # q = _fts_query(query); if q is None: return ()
        # rows = run search SQL; return tuple(MemoryHit(MemoryKind(kind), key, body) for ...)

    async def preamble(self, *, max_chars: int) -> str:
        """Facts, most recently updated first, formatted for a system prompt, cut at whole
        lines to ``max_chars``. Empty string when there are no facts. Snippets are never included."""
        raise NotImplementedError
        # lines = ["Durable facts the user asked you to remember (most recent first):"]
        # for key, value in rows: line = f"- {key}: {value}"; stop when total + len(line) > max_chars


def normalize_key(raw: str) -> str | None:
    """'Paths.Trade' -> 'paths.trade'; 'trading project' -> 'general.trading_project';
    lowercase, inner whitespace -> '_', strip non [a-z0-9_.-], collapse dots, default
    namespace 'general'. None if nothing alphanumeric remains."""
    raise NotImplementedError


def _fts_query(text: str) -> str | None:
    """Free text -> safe FTS5 MATCH expression.

    tokens = re.findall(r"\\w+", text.lower(), re.UNICODE) minus STOPWORDS (keep all if that
    empties it); each token double-quoted (a quoted string is a phrase: no operator, no
    column filter, no prefix star can survive) and OR-joined so BM25 ranks partial matches:
    'where\\'s my "trading" project?' -> '"trading" OR "project"'. None if no tokens.
    """
    raise NotImplementedError
