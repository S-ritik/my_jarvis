"""Composition root for ``jarvis run``: the only module that knows every concrete class.

Order matters and is encoded here once: lock -> memory -> adapters (model loads) -> core
-> server. Tests build their own composition from fakes (``tests/fakes.py``) and the
same ``AssistantCore`` / ``ControlServer``.
"""

from __future__ import annotations

from collections.abc import MutableMapping
from typing import Final

from jarvis.core.bus import EventSubscription
from jarvis.settings import LoggingSettings, Settings

BILLING_VARIABLES: Final = (
    "ANTHROPIC_API_KEY",
    "ANTHROPIC_AUTH_TOKEN",
    "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_USE_BEDROCK",
    "CLAUDE_CODE_USE_VERTEX",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
)
"""Removed from the daemon's environment so every brain bills the user's subscription (ADR 01)."""

PR_SET_NO_NEW_PRIVS: Final = 38


def harden_process(environ: MutableMapping[str, str]) -> tuple[str, ...]:
    """Run once, first thing in ``jarvis run``, before any adapter or subprocess exists.

    1. Delete ``BILLING_VARIABLES`` from ``environ`` (the real ``os.environ``). The Claude
       Agent SDK builds the CLI's env as ``{**os.environ, **options.env}`` and cannot remove
       a variable, so the daemon's own environment is the only place to do it.
    2. ``prctl(PR_SET_NO_NEW_PRIVS, 1)`` on the daemon: every brain process tree inherits
       it, so setuid binaries (``sudo``, ``su``, ``pkexec``) cannot escalate even if the
       Safety Gate misses a command. Nothing JARVIS runs itself needs setuid (``wpctl``,
       ``playerctl``, ``systemd-run --user``); desktop apps are launched through the user
       session manager, so they do not inherit the flag.

    Returns the names that were removed (``doctor`` and the log report them; values never
    leave this function).
    """
    raise NotImplementedError
    # removed = tuple(n for n in BILLING_VARIABLES if environ.pop(n, None) is not None)
    # libc = ctypes.CDLL(None, use_errno=True)
    # if libc.prctl(PR_SET_NO_NEW_PRIVS, 1, 0, 0, 0) != 0: raise OSError(ctypes.get_errno(), "prctl")
    # return removed


async def run_daemon(settings: Settings) -> int:
    """Run until SIGINT/SIGTERM. Returns the process exit code.

    The caller (``jarvis.cli``) has already run ``harden_process(os.environ)``."""
    raise NotImplementedError
    # clock = SystemClock()
    # try: lock = InstanceLock.acquire(settings.paths.runtime_dir, settings.control.socket_name)
    # except DaemonAlreadyRunning as e: print(e, file=sys.stderr); return 1
    # with lock:
    #     memory = await MemoryStore.open(settings.memory.db_path, now=clock.now)       # MemoryUnavailable -> exit 1
    #     ports = Ports(microphone=SoundDeviceMicrophone(...), wake=await OpenWakeWordScorer.load(...),
    #                   vad=await SileroVadScorer.load(...), transcriber=await WhisperTranscriber.load(...),
    #                   brains={CLAUDE_CODE: ClaudeCodeBackend(...), ANTIGRAVITY: AntigravityBackend(...)},
    #                   synthesizer=await PiperSynthesizer.load(...), player=SoundDevicePlayer(...),
    #                   clips=DecodingClipLoader(...), desktop=LinuxDesktop(...),
    #                   context=MemoryContext(memory, settings.memory), audit=FileAuditLog(...),
    #                   clock=clock, rng=random.Random())
    #     core = AssistantCore(ports, settings)
    #     journal = core.subscribe(capacity=None)
    #     async with asyncio.TaskGroup() as tg, core, ControlServer.serving(core, lock, settings.control):
    #         tg.create_task(write_journal(journal, settings.logging, settings.paths.turn_log))
    #         await until_signalled(SIGINT, SIGTERM)
    # return 0


async def write_journal(events: EventSubscription, settings: LoggingSettings, path: object) -> None:
    """The structured per-turn log: one JSON line per ``TurnFinished`` with its timings,
    transcripts unless ``log_transcripts`` is off, errors and refusals. Audio is never logged."""
    raise NotImplementedError
