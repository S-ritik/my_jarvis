# Linux Audio IO and Mic Concurrency Stack

Type: research
Status: resolved
Blocked by: none

## Question

What is the optimal Python audio capture and playback library (`sounddevice` vs `pyaudio` vs direct PipeWire ALSA loop) on this Linux laptop (with PipeWire/PulseAudio) that supports continuous background mic streaming for wake-word detection without locking the audio device when text-to-speech plays simultaneously?

## Answer

- **Library**: `sounddevice` (backed by PortAudio + CFFI). It provides native NumPy array buffers (zero-copy), supports Python 3.14+, and avoids GIL pressure or memory fragmentation during 24/7 background streaming. Avoid PyAudio (legacy C extension, byte copying GC churn) and native ALSA C loops (device locking bugs).
- **Concurrency & Locking**: Decoupled independent streams. Open a continuous `sd.InputStream` targeting `device='default'` (16,000 Hz, 1 channel, `int16`, block size 1280 samples / 80ms) for Wake Word and VAD. Play TTS on demand via `sd.play()`. PipeWire multiplexes both virtual nodes seamlessly without ALSA `EBUSY` hardware conflicts.
- **Resampling Strategy**: Server-side delegation. PipeWire automatically resamples between the physical 48kHz microphone clock and the requested 16kHz capture stream, and between Piper TTS (22.05kHz/24kHz) and speakers in SIMD C (<0.05% CPU), requiring zero resampling math in Python.
- **Acoustic Feedback**: Implement a state gate (`LISTENING`, `THINKING`, `SPEAKING`) with a 250ms post-playback hangover delay to discard speaker echo during TTS output. For true live barge-in in later iterations, load PipeWire's WebRTC AEC module (`pw-cli load-module libpipewire-module-echo-cancel`).
