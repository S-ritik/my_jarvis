"""The Safety Gate (ADR 06, strict zero-sudo, Option B): a pure verdict function.

Knowledge owned here: the denylist categories, shell-aware splitting (pipelines, ``;``,
``&&``, ``||``, subshells, ``$(...)``, backticks, ``bash -c``/``sh -c`` payloads),
wrapper unwrapping (``env``, ``xargs``, ``nohup``, ``timeout``, ``nice``, ``exec``,
``command``, ``builtin``), basename reduction of binary paths, protected directories,
workspace-root rules for deletion, and the message the agent receives on a deny.

What it does *not* own: what happens after a deny (cue, fixed line, discard, audit).
That is turn policy in ``AssistantCore``; the gate stays pure so its adversarial table
can be fed through the core seam as Brain tool requests and assert on the verdict
*and* the spoken consequences.

The denylist is the first filter and the UX. The boundary is ``no_new_privs`` on the
daemon, inherited by every brain process tree (``jarvis.daemon.harden_process``), plus
ordinary Unix permissions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Final, TypeAlias

from jarvis.brain.port import (
    Allow,
    Deny,
    DenyCategory,
    EditFile,
    ReadFile,
    RunShell,
    SearchFiles,
    ToolAction,
    ToolVerdict,
    UnknownTool,
    UseCustomTool,
    UseWeb,
    WriteFile,
)
from jarvis.settings import SafetySettings

PRIVILEGE_ESCALATION: Final = frozenset({"sudo", "su", "doas", "pkexec", "run0"})
DESTRUCTIVE_DISK: Final = frozenset({"dd", "fdisk", "sfdisk", "gdisk", "parted", "wipefs"})
"""Plus any basename starting with ``mkfs``, and writes/redirects to ``/dev/sd*``, ``/dev/nvme*``, ``/dev/vd*``, ``/dev/mmcblk*``."""
WRAPPERS: Final = frozenset({"env", "xargs", "nohup", "timeout", "nice", "exec", "command", "builtin", "stdbuf", "ionice"})
SHELLS: Final = frozenset({"sh", "bash", "dash", "zsh", "fish", "ksh"})
MUTATORS: Final = frozenset({"rm", "mv", "cp", "install", "ln", "chmod", "chown", "chgrp", "touch", "mkdir", "rmdir", "tee", "truncate", "sed"})
"""Commands whose path operands count as writes for the system-directory rule (``sed`` only with ``-i``)."""

AGENT_DENIAL: Final = (
    "Refused by the JARVIS safety policy ({category}). The user must run this manually in a "
    "terminal. Do not retry it and do not try to achieve the same effect another way."
)


@dataclass(frozen=True)
class _SimpleCommand:
    """One simple command after splitting and unwrapping."""

    argv: tuple[str, ...]
    """``argv[0]`` reduced to its basename; wrappers removed."""
    redirect_targets: tuple[str, ...]
    """Paths written by ``>``, ``>>``, ``&>`` (``2>&1`` and ``/dev/null`` excluded)."""
    piped_into: str | None
    """Basename of the next command in the pipeline, if any (detects ``... | sh``)."""


@dataclass(frozen=True)
class _Unparseable:
    reason: str


_ShellAnalysis: TypeAlias = tuple[_SimpleCommand, ...] | _Unparseable


class SafetyGate:
    """``check(action) -> Allow | Deny``. Pure, deterministic, no I/O, no environment reads."""

    def __init__(self, settings: SafetySettings) -> None:
        raise NotImplementedError
        # home, roots, protected dirs and the allowlist come from settings (resolved at load)

    def check(self, action: ToolAction) -> ToolVerdict:
        raise NotImplementedError
        # match action:
        #   case RunShell(command=c):
        #       match _analyse_shell(c):
        #           case _Unparseable(): return deny(UNINSPECTABLE)
        #           case cmds: first non-None of _check_simple(cmd) for cmd in cmds, else Allow()
        #     (requires SHELL in allowlist, else deny(OUTSIDE_ALLOWLIST))
        #   case WriteFile(path=p) | EditFile(path=p): deny(SYSTEM_DIRECTORY) if _protected(p) else Allow()
        #   case ReadFile() | SearchFiles() | UseWeb(): Allow() if family in allowlist else deny(OUTSIDE_ALLOWLIST)
        #   case UseCustomTool(): Allow()          # only SessionSpec.tools can be named here
        #   case UnknownTool(): deny(OUTSIDE_ALLOWLIST)
        #   case _: assert_never(action)

    def _check_simple(self, cmd: _SimpleCommand) -> Deny | None:
        raise NotImplementedError
        # name = cmd.argv[0]
        # if name in PRIVILEGE_ESCALATION: PRIVILEGE_ESCALATION
        # if cmd.piped_into in SHELLS: UNINSPECTABLE                  # curl ... | bash
        # if name in DESTRUCTIVE_DISK or name.startswith("mkfs") or any(_is_block_device(t) for t in redirects+of=): DESTRUCTIVE_DISK
        # if name == "rm" and (recursive or wildcard) and not all(_inside_roots(t) for t in targets): UNCONSTRAINED_DELETION
        # if name == "rm" and any(t in {"/", "~", "$HOME", home, *roots}): UNCONSTRAINED_DELETION
        # if name == "find" and "-delete" in argv and not _inside_roots(start): UNCONSTRAINED_DELETION
        # if any(_protected(p) for p in redirect_targets + mutated_operands(cmd)): SYSTEM_DIRECTORY
        # return None

    def _protected(self, path: str) -> bool:
        raise NotImplementedError  # expand ~/$HOME lexically (no filesystem access), normalize, is under a protected dir


def _analyse_shell(command: str) -> _ShellAnalysis:
    """Split a command line into simple commands, recursing into ``$(...)``, backticks,
    subshells and ``sh -c``/``bash -c`` payloads, and unwrapping wrapper commands.
    Any construct it cannot tokenize with confidence (unbalanced quotes, heredocs feeding
    a shell, ``eval``) yields ``_Unparseable``. Private: the adversarial table drives it
    through the core seam (``SafetyGate.check`` via Brain tool requests)."""
    raise NotImplementedError


__all__ = ["SafetyGate", "AGENT_DENIAL"]
