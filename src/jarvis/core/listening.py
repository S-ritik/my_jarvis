"""Listening-side policy: everything measured in audio samples.

Knowledge owned here (and nowhere else): wake threshold + consecutive-frame debounce +
refractory with scorer reset (ADR 03); the 0.5 s pre-roll ring; the wake-ack window;
speech onset/silence hysteresis; the two endpoint tiers chosen by cumulative voiced
duration; the 15 s ceiling; the 5 s no-speech timeout; the 250 ms post-playback
hangover; and the rule that muted (gated) time never counts as silence or toward a
timeout. The only clock is the number of samples ``hear`` has been given.

The core decides *when* the listener is idle, capturing or paused (that is turn state);
the listener decides *what the audio means*.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from jarvis.audio import AudioFrame, Pcm
from jarvis.core.ports import VadScorer, WakeScorer
from jarvis.core.vocabulary import CaptureEnd
from jarvis.settings import ListeningSettings


@dataclass(frozen=True)
class Nothing:
    pass


@dataclass(frozen=True)
class WakeHeard:
    """Detection. The listener has already switched itself to wake-capture (pre-roll + ack window)."""

    score: float


@dataclass(frozen=True)
class AckDue:
    """The ack window passed without speech onset. The listener has muted itself until
    ``speaker_drained()``; the core should play the ``wake_ack`` cue now."""


@dataclass(frozen=True)
class Utterance:
    """Capture ended; the listener has paused itself. ``audio`` starts with the pre-roll."""

    audio: Pcm
    end: CaptureEnd
    voiced_ms: int
    captured_ms: int


@dataclass(frozen=True)
class NoSpeech:
    """No speech onset within the no-speech timeout; the listener has paused itself."""


Heard: TypeAlias = Nothing | WakeHeard | AckDue | Utterance | NoSpeech


class Listener:
    """Sample-clocked listening policy over the two per-frame scorers.

    Modes (internal): WAKE (score wake word, fill pre-roll), CAPTURE (score VAD, endpoint),
    PAUSED (discard; nothing advances). Independently, a *mute* is applied while a cue it
    asked for is playing and a *hangover* of ``playback_hangover_ms`` samples is discarded
    after every ``speaker_drained()``.
    """

    def __init__(self, settings: ListeningSettings, wake: WakeScorer, vad: VadScorer) -> None:
        raise NotImplementedError
        # convert every *_ms setting to samples once (audio.ms_to_samples)

    async def hear(self, frame: AudioFrame) -> Heard:
        """Feed one capture frame. Returns at most one signal."""
        raise NotImplementedError
        # if paused or muted: return Nothing()                      # gated time never counts
        # if hangover_left > 0: hangover_left -= len(frame); return Nothing()
        # refractory_left = max(0, refractory_left - len(frame))
        # WAKE:
        #   preroll.append(frame)                                   # ring of preroll_ms
        #   s = await wake.score(frame)
        #   if refractory_left > 0: return Nothing()
        #   streak = streak + 1 if s >= threshold else 0
        #   if streak >= consecutive_frames:
        #       wake.reset(); refractory_left = refractory; streak = 0
        #       begin_capture(with_preroll=True, ack_window=True); return WakeHeard(s)
        # CAPTURE:
        #   p = await vad.speech_probability(frame); captured += n; buffer.append(frame)
        #   voiced: p >= onset; silent: p < silence (between: keep previous label)
        #   if voiced: onset_seen = True; voiced_total += n; silence_run = 0
        #   elif silent and onset_seen: silence_run += n
        #   if not onset_seen:
        #       if ack_window_open and captured >= ack_window: ack_window_open = False; muted = True; return AckDue()
        #       if captured_without_onset >= no_speech_timeout: pause(); return NoSpeech()
        #   tier = flowing if voiced_total >= flowing_after_voiced else short
        #   if onset_seen and silence_run >= tier: pause(); return Utterance(concat(preroll+buffer), ENDPOINT, ...)
        #   if captured >= ceiling: pause(); return Utterance(..., CEILING, ...)
        #   if onset_seen and ack_window_open: ack_window_open = False      # speech within window: no cue
        #   return Nothing()

    def idle(self) -> None:
        """Back to wake listening (turn over, ``stop``, after ``wake``). Clears capture state."""
        raise NotImplementedError

    def start_capture(self) -> None:
        """Push-to-talk: capture now, no pre-roll, no ack window, short tier first."""
        raise NotImplementedError  # vad.reset(); wake.reset(); mode = CAPTURE

    def pause(self) -> None:
        """Thinking/Speaking: discard frames until ``idle()`` or ``start_capture()``."""
        raise NotImplementedError

    def speaker_drained(self) -> None:
        """All playback ended: lift a cue mute and discard the next ``playback_hangover_ms`` of audio."""
        raise NotImplementedError
