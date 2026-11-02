"""The Brain backend port: the vendor-neutral contract every agent backend implements.

Knowledge owned here: what a Brain *is* to JARVIS (a persistent agent session that
streams text, runs gated tools and fails in five typed ways). Knowledge hidden behind
it: which vendor, which process, which SDK message types, which tool names.

Nothing in this module imports a vendor. ``claude_agent_sdk`` types exist only in
``jarvis.brain.claude``; Antigravity's transport only in ``jarvis.brain.antigravity``.

Contract summary (the core's ``Personas`` is the only caller and upholds the caller side):

1. ``BrainBackend.probe()`` is cheap and side-effect free; it is called at boot, by
   ``doctor``, and again when switching to a persona whose backend was unavailable.
2. ``BrainBackend.open(spec)`` starts one persistent session. Every tool call the
   session's agent attempts MUST be passed to ``spec.gate`` before it executes.
   A backend declares what it can honour in ``capabilities``; the *caller* (``Personas``)
   enforces the consequence, so an adapter author cannot forget it:
   ``gates_tools=False`` -> the session is opened with no built-in tools at all;
   ``custom_tools=False`` -> no ``SessionSpec.tools`` (the memory preamble still applies).
3. ``BrainSession.send(text)`` yields one turn: ``TextDelta``/``ToolFinished`` events,
   then exactly one terminal event (``TurnEnded`` or ``BrainFailed``), then stops.
   Only one turn is in flight per session. The caller always iterates to the terminal
   event (also after ``interrupt()``), so a backend never has to buffer a stale turn.
4. ``interrupt()`` is only meaningful while a turn is in flight and only when
   ``interruptible`` is true; it makes the turn end soon with ``TurnEnded(interrupted=True)``.
5. Failures are values (``BrainFailed`` / ``BrainError``), never vendor exceptions.
6. A session may be driven from any task: ``send``/``interrupt``/``close`` can be called
   from tasks other than the one that called ``open``, and the stream ``send`` returns is
   not bound to the consuming task. Adapters whose vendor client is task-affine (the
   Claude Agent SDK's ``ClaudeSDKClient`` must be used in the async context that connected
   it) host the client in their own long-lived task and bridge to it with queues. Never
   hand a vendor async generator to the caller.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Protocol, TypeAlias

type JsonValue = str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
JsonObject: TypeAlias = dict[str, JsonValue]


class BackendKind(StrEnum):
    CLAUDE_CODE = "claude_code"
    ANTIGRAVITY = "antigravity"


# --------------------------------------------------------------------------- availability


@dataclass(frozen=True)
class Available:
    pass


@dataclass(frozen=True)
class Unavailable:
    reason: str
    """One short sentence, spoken as-is: "Antigravity is not installed."."""
    fix: str
    """Suggested fix shown by ``jarvis doctor``."""


Availability: TypeAlias = Available | Unavailable


# --------------------------------------------------------------------------- tools offered to a session


class BuiltinTool(StrEnum):
    """Vendor-neutral names for the agent's built-in tool families (the session allowlist).

    Each adapter maps these to its own tool names; the core and settings never see those.
    """

    SHELL = "shell"
    READ = "read"
    WRITE = "write"
    EDIT = "edit"
    SEARCH = "search"
    WEB = "web"


@dataclass(frozen=True)
class ToolOutput:
    text: str
    failed: bool


@dataclass(frozen=True)
class BrainTool:
    """A custom tool JARVIS implements in-process (e.g. ``save_memory``).

    ``parameters`` is a JSON Schema object. The adapter registers the tool under the
    plain ``name`` from the model's point of view (Claude: in-process SDK MCP server).
    """

    name: str
    description: str
    parameters: JsonObject
    handler: Callable[[JsonObject], Awaitable[ToolOutput]]


# --------------------------------------------------------------------------- tool calls the gate judges


@dataclass(frozen=True)
class RunShell:
    command: str


@dataclass(frozen=True)
class WriteFile:
    path: str


@dataclass(frozen=True)
class EditFile:
    path: str


@dataclass(frozen=True)
class ReadFile:
    path: str


@dataclass(frozen=True)
class SearchFiles:
    pattern: str
    root: str | None


@dataclass(frozen=True)
class UseWeb:
    target: str


@dataclass(frozen=True)
class UseCustomTool:
    """A call to one of ``SessionSpec.tools`` (by its plain name)."""

    name: str


@dataclass(frozen=True)
class UnknownTool:
    """Anything the adapter cannot classify. The Safety Gate denies it (outside allowlist)."""

    name: str


ToolAction: TypeAlias = (
    RunShell | WriteFile | EditFile | ReadFile | SearchFiles | UseWeb | UseCustomTool | UnknownTool
)
"""Closed, vendor-neutral classification of a tool call. Adding a family = add a variant;
the type checker then flags the Safety Gate's and the adapters' matches."""


@dataclass(frozen=True)
class ToolCall:
    call_id: str
    vendor_name: str
    """The backend's own tool name, for the audit log only (e.g. ``Bash``)."""
    action: ToolAction
    raw_input: JsonObject
    """The full request as the agent sent it, for the audit log only."""


class DenyCategory(StrEnum):
    PRIVILEGE_ESCALATION = "privilege_escalation"
    DESTRUCTIVE_DISK = "destructive_disk"
    UNCONSTRAINED_DELETION = "unconstrained_deletion"
    SYSTEM_DIRECTORY = "system_directory"
    UNINSPECTABLE = "uninspectable"
    """Unparseable shell, or a pipe into a shell interpreter."""
    OUTSIDE_ALLOWLIST = "outside_allowlist"
    TURN_CANCELLED = "turn_cancelled"
    """Not a safety refusal: the user stopped the turn this call belongs to. Never spoken."""


@dataclass(frozen=True)
class Allow:
    pass


@dataclass(frozen=True)
class Deny:
    category: DenyCategory
    message_to_agent: str
    """Delivered to the model as the tool's error: "run it manually; do not retry"."""


ToolVerdict: TypeAlias = Allow | Deny

PermissionGate: TypeAlias = Callable[[ToolCall], Awaitable[ToolVerdict]]
"""Awaited on the daemon's event loop, before the tool executes, for every tool call."""


# --------------------------------------------------------------------------- session spec


@dataclass(frozen=True)
class SessionSpec:
    model: str
    system_prompt: str
    builtins: frozenset[BuiltinTool]
    tools: tuple[BrainTool, ...]
    gate: PermissionGate
    workspace: Path
    """Working directory of the agent (the configured default workspace root)."""


# --------------------------------------------------------------------------- stream events


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class ToolFinished:
    call_id: str
    succeeded: bool


@dataclass(frozen=True)
class TurnEnded:
    interrupted: bool


class BrainErrorKind(StrEnum):
    AUTH = "auth"
    USAGE_LIMIT = "usage_limit"
    UNAVAILABLE = "unavailable"
    CRASHED = "crashed"
    """The session is dead; the core reopens it on the persona's next turn (context lost)."""
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class BrainError:
    kind: BrainErrorKind
    detail: str
    """For the log; never spoken (the core owns spoken phrasing)."""
    retry_at: datetime | None
    """Only for USAGE_LIMIT, when the backend reports a reset time."""


@dataclass(frozen=True)
class BrainFailed:
    error: BrainError


BrainEvent: TypeAlias = TextDelta | ToolFinished | TurnEnded | BrainFailed
""""Tool requested" is deliberately not a stream event: the permission gate *is* the
request, so there is exactly one place a tool call can be observed and it cannot be skipped."""


# --------------------------------------------------------------------------- the port


class BrainSession(Protocol):
    @property
    def interruptible(self) -> bool: ...

    def send(self, text: str) -> AsyncIterator[BrainEvent]:
        """Run one turn. See module docstring, rule 3."""
        ...

    async def interrupt(self) -> None: ...

    async def close(self) -> None: ...


@dataclass(frozen=True)
class BackendCapabilities:
    """What a backend can honour (rule 2). Data, not modes: ``Personas`` reads it once per
    ``open`` and narrows the ``SessionSpec`` accordingly."""

    gates_tools: bool
    """Calls ``spec.gate`` before *every* built-in tool executes. False -> no built-ins."""
    custom_tools: bool
    """Can host ``BrainTool``s in-process (Claude: SDK MCP server). False -> no custom tools."""


class BrainBackend(Protocol):
    @property
    def kind(self) -> BackendKind: ...

    @property
    def capabilities(self) -> BackendCapabilities: ...

    async def probe(self) -> Availability: ...

    async def open(self, spec: SessionSpec) -> BrainSession | BrainError: ...
