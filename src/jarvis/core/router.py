"""Transcript normalization and the Zero-Latency Bypass grammar.

Knowledge owned here: which leading wake phrases are stripped; what counts as empty or
wordless; the cancel phrases; and the ordered list of whole-utterance grammar rules that
map a normalized transcript to a ``Route``. No LLM, no I/O: app names resolve against an
``AppDirectory`` snapshot and persona names against the persona alias table.

To add a bypass intent: append one ``Rule`` to ``RULES`` (the nearest example is right
above it). If it needs a new side effect, add a ``DesktopIntent`` variant in
``core.vocabulary``; the type checker then points at the one adapter ``match`` to extend.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Final

from jarvis.core.vocabulary import (
    Act,
    Answer,
    AppDirectory,
    Control,
    ControlMedia,
    Dismiss,
    DismissReason,
    LocalQuery,
    MediaAction,
    PersonaName,
    Route,
    SetMute,
    SetVolume,
    Sleep,
    StepVolume,
    SwitchPersona,
    Think,
    VolumeDirection,
)

WAKE_PHRASES: Final = ("hey jarvis", "hi jarvis", "okay jarvis", "jarvis")
CANCEL_PHRASES: Final = ("never mind", "nevermind", "cancel", "forget it")


@dataclass(frozen=True)
class RouteContext:
    personas: Mapping[str, PersonaName]
    """Lowercase alias -> persona."""
    apps: AppDirectory


@dataclass(frozen=True)
class Rule:
    """One whole-utterance grammar rule. ``pattern`` must ``fullmatch`` the normalized text.

    ``build`` returns ``None`` to decline (e.g. unknown app name), which lets the
    utterance fall through to later rules and finally to the Brain.
    """

    name: str
    pattern: re.Pattern[str]
    build: Callable[[re.Match[str], RouteContext], Route | None]


def _const(route: Route) -> Callable[[re.Match[str], RouteContext], Route | None]:
    return lambda _m, _ctx: route


def _persona(m: re.Match[str], ctx: RouteContext) -> Route | None:
    raise NotImplementedError  # p = ctx.personas.get(m["name"]); Control(SwitchPersona(p)) if p else None


def _launch(m: re.Match[str], ctx: RouteContext) -> Route | None:
    raise NotImplementedError  # app = ctx.apps.find(m["app"]); Act(LaunchApp(app)) if app else None


def _set_volume(m: re.Match[str], ctx: RouteContext) -> Route | None:
    raise NotImplementedError  # pct = int(m["pct"]) (also "forty" via a small number-word table); 0..100 else None


_P = re.compile

RULES: Final[tuple[Rule, ...]] = (
    Rule("persona", _P(r"(?:switch|change) to (?:the )?(?P<name>[a-z ]+?)(?: mode| persona)?"), _persona),
    Rule("volume_up", _P(r"(?:turn (?:the )?)?volume up|louder|turn it up"), _const(Act(StepVolume(VolumeDirection.UP)))),
    Rule("volume_down", _P(r"(?:turn (?:the )?)?volume down|quieter|turn it down"), _const(Act(StepVolume(VolumeDirection.DOWN)))),
    Rule("volume_set", _P(r"(?:set )?(?:the )?volume to (?P<pct>\w+)(?: percent| %)?"), _set_volume),
    Rule("mute", _P(r"mute(?: the)?(?: sound| audio| volume)?"), _const(Act(SetMute(True)))),
    Rule("unmute", _P(r"unmute(?: the)?(?: sound| audio| volume)?"), _const(Act(SetMute(False)))),
    Rule("play", _P(r"(?:play|resume)(?: the)?(?: music| media)?"), _const(Act(ControlMedia(MediaAction.PLAY)))),
    Rule("pause", _P(r"pause(?: the)?(?: music| media)?|stop the music"), _const(Act(ControlMedia(MediaAction.PAUSE)))),
    Rule("next", _P(r"(?:next|skip)(?: track| song)?"), _const(Act(ControlMedia(MediaAction.NEXT)))),
    Rule("previous", _P(r"previous(?: track| song)?|go back a (?:track|song)"), _const(Act(ControlMedia(MediaAction.PREVIOUS)))),
    Rule("time", _P(r"what(?:'s| is) the time|what time is it"), _const(Answer(LocalQuery.TIME))),
    Rule("date", _P(r"what(?:'s| is) (?:the )?(?:date|day)(?: today)?|what day is it"), _const(Answer(LocalQuery.DATE))),
    Rule("launch", _P(r"(?:open|launch|start) (?P<app>[a-z0-9 .+-]+)"), _launch),
    Rule("sleep", _P(r"go to sleep|sleep now"), _const(Control(Sleep()))),
)


class Router:
    """Pure: ``route(raw_transcript)`` -> ``(normalized_text, Route)``."""

    def __init__(self, context: RouteContext, rules: tuple[Rule, ...] = RULES) -> None:
        raise NotImplementedError

    def route(self, raw: str) -> tuple[str, Route]:
        raise NotImplementedError
        # text = normalize(raw)        # lowercase copy for matching; strip leading WAKE_PHRASES
        #                              # (with trailing punctuation), collapse whitespace, strip
        #                              # trailing ".?!" for matching only
        # if not any(ch.isalpha() for ch in text): return text, Dismiss(EMPTY)
        # if match_text in CANCEL_PHRASES: return text, Dismiss(CANCELLED)
        # for rule in rules:
        #     if m := rule.pattern.fullmatch(match_text):
        #         if (r := rule.build(m, context)) is not None: return text, r
        # return text, Think(text)     # brain gets the original-case normalized text
