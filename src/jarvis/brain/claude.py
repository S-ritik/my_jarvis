"""Claude Code backend, via the Claude Agent SDK (claude-agent-sdk 0.2.176).

The only module that imports ``claude_agent_sdk``. Knowledge owned here: the SDK's
options, message types and errors; Claude Code's tool names; how JARVIS's vendor-neutral
allowlist, custom tools and permission gate are expressed to the CLI; how the SDK's
stream is reduced to ``BrainEvent``s; and how its failures become ``BrainErrorKind``s.

Session wiring (one ``ClaudeSDKClient`` per persona per voice run)::

    ClaudeAgentOptions(
        model=spec.model,
        system_prompt=spec.system_prompt,             # plain string: no Claude Code preset, voice-first
        tools=[name for b in spec.builtins for name in BUILTIN_NAMES[b]],   # what exists at all
        allowed_tools=[],                             # NOTHING auto-approved: every call reaches the gate
        permission_mode="default",
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[pre_tool_use])]},   # every tool, incl. reads
        can_use_tool=can_use_tool,                    # backstop for anything that still asks
        mcp_servers={"jarvis": create_sdk_mcp_server("jarvis", tools=[...spec.tools...])},
        setting_sources=[],                           # isolated: None would load ALL user/project settings
        cwd=spec.workspace,
        cli_path=settings.cli_path,                   # None = the CLI bundled with the SDK
        include_partial_messages=True,                # StreamEvent text deltas
        stderr=log_line,
    )

Subscription-only billing and ``no_new_privs`` are *not* handled here: the SDK builds the
child environment as ``{**os.environ, **options.env}`` (it can override a variable, never
remove one) and has no pre-exec hook. ``jarvis.daemon.harden_process`` therefore removes the
billing variables from the daemon's own environment and sets ``no_new_privs`` on the daemon
at startup, so every brain process tree inherits both.

Session hosting (port rule 6): ``ClaudeSDKClient`` keeps an internal task group from
``connect()`` to ``disconnect()`` and must be used in that async context. Each session is
therefore one long-lived *host task* created by ``open``::

    host task:  async with ClaudeSDKClient(options) as client:      # connect here, once
                    signal opened (or BrainError) to open()
                    loop: request = await requests.get()             # Send(text, events) | Interrupt | Close
                          Send      -> await client.query(text)
                                       async for msg in client.receive_response():
                                           for ev in reduce(msg): events.put_nowait(ev)
                                       (exactly one terminal event is always put)
                          Interrupt -> await client.interrupt()
                          Close     -> break                         # __aexit__ disconnects here

``_ClaudeSession.send`` enqueues ``Send`` and yields from that turn's ``events`` queue, so
the caller (a ``Personas`` pump task) never touches the client.

Gate bridge: the PreToolUse hook (and, as a backstop, ``can_use_tool``) builds a
``ToolCall`` from ``(tool_name, tool_input, tool_use_id)``, awaits ``spec.gate`` and answers
``permissionDecision: "allow" | "deny"`` with ``permissionDecisionReason =
Deny.message_to_agent`` (the model sees the reason and the tool does not run).

Stream reduction (``send``)::

    StreamEvent content_block_delta/text_delta       -> TextDelta(text)
    AssistantMessage TextBlock                       -> ignored (already streamed as deltas)
    AssistantMessage.error                           -> BrainFailed(kind per ERROR_KINDS)
    UserMessage ToolResultBlock(tool_use_id, is_error)-> ToolFinished(id, not is_error)
    RateLimitEvent(status="rejected", resets_at)     -> BrainFailed(USAGE_LIMIT, retry_at)
    ResultMessage(is_error, api_error_status=429)    -> BrainFailed(USAGE_LIMIT)
    ResultMessage(is_error, api_error_status=401)    -> BrainFailed(AUTH)
    ResultMessage(is_error, other)                   -> BrainFailed(CRASHED)
    ResultMessage(terminal_reason="aborted_*")       -> TurnEnded(interrupted=True)
    ResultMessage(otherwise)                         -> TurnEnded(interrupted=False)
    CLIConnectionError / ProcessError mid-turn       -> BrainFailed(CRASHED)
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from pathlib import Path
from typing import Any, Final

from claude_agent_sdk import (  # vendor types stay in this module
    ClaudeAgentOptions,
    ClaudeSDKClient,
    HookMatcher,
    PermissionResultAllow,
    PermissionResultDeny,
    ToolPermissionContext,
)

from jarvis.brain.port import (
    Availability,
    BackendCapabilities,
    BackendKind,
    BrainError,
    BrainErrorKind,
    BrainEvent,
    BrainSession,
    BuiltinTool,
    JsonObject,
    SessionSpec,
    ToolAction,
    ToolCall,
)
from jarvis.settings import ClaudeSettings

BUILTIN_NAMES: Final[Mapping[BuiltinTool, tuple[str, ...]]] = {
    BuiltinTool.SHELL: ("Bash",),
    BuiltinTool.READ: ("Read",),
    BuiltinTool.WRITE: ("Write",),
    BuiltinTool.EDIT: ("Edit", "MultiEdit", "NotebookEdit"),
    BuiltinTool.SEARCH: ("Grep", "Glob"),
    BuiltinTool.WEB: ("WebSearch", "WebFetch"),
}

ERROR_KINDS: Final[Mapping[str, BrainErrorKind]] = {
    "authentication_failed": BrainErrorKind.AUTH,
    "billing_error": BrainErrorKind.USAGE_LIMIT,
    "rate_limit": BrainErrorKind.USAGE_LIMIT,
    "server_error": BrainErrorKind.UNAVAILABLE,
    "invalid_request": BrainErrorKind.CRASHED,
    "unknown": BrainErrorKind.CRASHED,
}

MCP_SERVER: Final = "jarvis"
"""Custom tools surface to the CLI as ``mcp__jarvis__<name>``; ``to_action`` maps them back."""


def to_action(tool_name: str, tool_input: Mapping[str, Any]) -> ToolAction:
    """Claude Code tool name + input -> vendor-neutral ``ToolAction``.

    Bash -> RunShell(command); Write -> WriteFile(file_path); Edit/MultiEdit/NotebookEdit ->
    EditFile(file_path|notebook_path); Read -> ReadFile; Grep/Glob -> SearchFiles;
    WebSearch/WebFetch -> UseWeb; mcp__jarvis__<n> -> UseCustomTool(n); else UnknownTool(name).
    A known tool with a malformed input (missing ``command``) becomes UnknownTool -> denied.
    """
    raise NotImplementedError


class ClaudeCodeBackend:
    """``BrainBackend`` for personas with ``backend = claude_code``."""

    def __init__(self, settings: ClaudeSettings) -> None:
        self._settings = settings

    @property
    def kind(self) -> BackendKind:
        return BackendKind.CLAUDE_CODE

    @property
    def capabilities(self) -> BackendCapabilities:
        return BackendCapabilities(gates_tools=True, custom_tools=True)

    async def probe(self) -> Availability:
        """CLI resolvable (bundled or configured) and runnable; logged in. Shared with ``doctor``,
        which additionally warns when an API-key variable is set in the user's shell."""
        raise NotImplementedError
        # missing CLI   -> Unavailable("Claude Code is not installed.", fix="pip install claude-agent-sdk / install the CLI")
        # logged out    -> Unavailable("Claude Code is logged out.", fix="run `claude` and log in")
        # (exact login check: ticket 1)

    async def open(self, spec: SessionSpec) -> BrainSession | BrainError:
        raise NotImplementedError
        # session = _ClaudeSession(ClaudeAgentOptions(...), spec)   (module docstring)
        # start session._host() as a task; await its "opened" signal
        # CLINotFoundError -> BrainError(UNAVAILABLE, ...); other connect failure -> BrainError(CRASHED, ...)
        # return session


class _ClaudeSession:
    """``BrainSession`` over one ``ClaudeSDKClient`` owned by this session's host task."""

    def __init__(self, options: ClaudeAgentOptions, spec: SessionSpec) -> None:
        self._options = options
        self._spec = spec
        # self._requests: asyncio.Queue[_Send | _Interrupt | _Close]; self._host_task

    @property
    def interruptible(self) -> bool:
        return True

    def send(self, text: str) -> AsyncIterator[BrainEvent]:
        raise NotImplementedError
        # events = asyncio.Queue[BrainEvent](); requests.put_nowait(_Send(text, events))
        # async generator: while True: ev = await events.get(); yield ev; if terminal: return
        # host task dead -> yield BrainFailed(CRASHED); return

    async def interrupt(self) -> None:
        raise NotImplementedError  # requests.put_nowait(_Interrupt())

    async def close(self) -> None:
        raise NotImplementedError  # requests.put_nowait(_Close()); await host task (bounded)

    async def _host(self) -> None:
        """The one task that connects, uses and disconnects the client (module docstring)."""
        raise NotImplementedError

    async def _pre_tool_use(self, input_data: Any, tool_use_id: str | None, context: Any) -> dict[str, Any]:
        """PreToolUse hook: the gate bridge for every tool call."""
        raise NotImplementedError
        # call = ToolCall(tool_use_id or uuid4().hex, name, to_action(name, tool_input), json_copy(tool_input))
        # match await spec.gate(call):
        #   Allow() -> {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "allow"}}
        #   Deny(_, msg) -> {"hookSpecificOutput": {"hookEventName": "PreToolUse",
        #                    "permissionDecision": "deny", "permissionDecisionReason": msg}}

    async def _can_use_tool(
        self, tool_name: str, tool_input: dict[str, Any], context: ToolPermissionContext
    ) -> PermissionResultAllow | PermissionResultDeny:
        """Backstop: same gate, same verdict mapping (``PermissionResultDeny(message, interrupt=False)``)."""
        raise NotImplementedError


def _json_copy(value: Mapping[str, Any]) -> JsonObject:
    """Deep-copy a vendor tool input into JSON-only values for ``ToolCall.raw_input``."""
    raise NotImplementedError

