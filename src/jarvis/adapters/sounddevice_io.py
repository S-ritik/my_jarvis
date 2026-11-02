"""Microphone and Player over sounddevice/PortAudio (PipeWire). The only module importing sounddevice."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AbstractAsyncContextManager

import sounddevice  # noqa: F401  (vendor import confined here)

from jarvis.audio import AudioFrame, PcmClip
from jarvis.core.ports import PlayerEvent
from jarvis.settings import AudioSettings


class SoundDeviceMicrophone:
    """``sd.InputStream(samplerate=16000, channels=1, dtype="int16", blocksize=1280)``.

    The PortAudio callback copies ``indata[:, 0]`` and calls
    ``loop.call_soon_threadsafe(queue.put_nowait, frame)``; nothing else. Overruns are logged.
    """

    def __init__(self, settings: AudioSettings) -> None:
        self._settings = settings

    def open(self) -> AbstractAsyncContextManager[AsyncIterator[AudioFrame]]:
        raise NotImplementedError


class SoundDevicePlayer:
    """One ``sd.OutputStream`` at a time, callback-fed from an item queue so items play
    back to back with no gap; reopened when an item's rate/channels differ. ``flush``
    zero-fills the callback and drops the queue (silence within one block, << 100 ms).
    Emits ``OutputLevel`` at ~30 Hz from the callback via ``call_soon_threadsafe``."""

    def __init__(self, settings: AudioSettings) -> None:
        self._settings = settings

    def enqueue(self, item_id: int, clip: PcmClip) -> None:
        raise NotImplementedError

    def flush(self) -> None:
        raise NotImplementedError

    def events(self) -> AsyncIterator[PlayerEvent]:
        raise NotImplementedError
