"""ClipLoader: decodes committed WAV/MP3 cue clips at native rate/channels (MP3 needs a decoder,
e.g. ``miniaudio`` or ``soundfile`` with libsndfile >= 1.1). The only module importing it."""

from __future__ import annotations

from pathlib import Path

from jarvis.audio import PcmClip


class DecodingClipLoader:
    def __init__(self, assets_root: Path) -> None:
        self._root = assets_root

    async def load(self, clip: str) -> PcmClip | None:
        raise NotImplementedError  # find <root>/<clip>.{wav,mp3}; decode to int16 (frames, channels) on a thread
