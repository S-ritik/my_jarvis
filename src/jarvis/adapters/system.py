"""Clock and AuditLog over the real system."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jarvis.core.ports import AuditEntry


class SystemClock:
    def monotonic(self) -> float:
        raise NotImplementedError  # time.monotonic()

    def now(self) -> datetime:
        raise NotImplementedError  # datetime.now().astimezone()

    async def sleep(self, seconds: float) -> None:
        raise NotImplementedError  # await asyncio.sleep(seconds)


class FileAuditLog:
    """JSON lines in ``$XDG_STATE_HOME/jarvis/safety-audit.jsonl`` (0600), appended on a worker thread."""

    def __init__(self, path: Path) -> None:
        self._path = path

    async def record(self, entry: AuditEntry) -> None:
        raise NotImplementedError
        # {"at": iso, "turn": n, "persona": p, "category": c, "tool": call.vendor_name, "input": call.raw_input}
