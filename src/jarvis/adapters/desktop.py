"""DesktopActions over wpctl (PipeWire), playerctl (MPRIS) and ``systemd-run --user`` (app launch).

The only module that knows these command lines and how to read XDG desktop entries.
Launches go to a transient user scope so apps outlive the daemon and do not inherit the
brain's ``no_new_privs``.
"""

from __future__ import annotations

from jarvis.core.vocabulary import ActionResult, AppDirectory, DesktopIntent
from jarvis.settings import DesktopSettings


class LinuxDesktop:
    def __init__(self, settings: DesktopSettings) -> None:
        self._settings = settings

    async def perform(self, intent: DesktopIntent) -> ActionResult:
        raise NotImplementedError
        # match intent:                                     (exhaustive; assert_never)
        #   StepVolume(UP|DOWN)  -> wpctl set-volume @DEFAULT_AUDIO_SINK@ 5%+|5%- (-l 1.0)
        #   SetVolume(p)         -> wpctl set-volume @DEFAULT_AUDIO_SINK@ {p}%
        #   SetMute(m)           -> wpctl set-mute @DEFAULT_AUDIO_SINK@ 1|0
        #   ControlMedia(a)      -> playerctl play|pause|next|previous ; "No players found" -> ActionFailed(NO_MEDIA_PLAYER)
        #   LaunchApp(app)       -> systemd-run --user --scope --collect -u app-jarvis-<id> gtk-launch <desktop_id>
        #   missing binary       -> ActionFailed(TOOL_MISSING)

    async def app_directory(self) -> AppDirectory:
        raise NotImplementedError  # settings.app_aliases + parse $XDG_DATA_DIRS/applications/*.desktop (Name, NoDisplay)
