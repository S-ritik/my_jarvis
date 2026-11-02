# JARVIS: Personal AI Assistant for Linux

A voice-driven desktop AI assistant running on Linux (Intel CPU, no GPU required), featuring:
- **Zero Paid APIs**: Bridges directly into your active **Claude Code** and **Google Antigravity** subscriptions.
- **Local Voice Privacy**: Speech-to-text (Faster-Whisper) and speech synthesis (Piper TTS) run 100% offline.
- **Holographic Desktop HUD**: Lightweight, transparent PyQt6 Arc Reactor overlay with live audio-reactive states (Idle, Listening, Thinking, Speaking).
- **Physical Remote Control**: Native **KDE Connect** commands for mobile/touch push-to-talk, mute/unmute, and sleep toggles.
- **Warcraft / Hearthstone Soundboard**: Pre-rendered authentic audio cues for lifecycle events (*"All defense systems online"*, *"As the master wills"*, *"Job's done!"*).
- **Sub-1.2s Latency**: Sentence-chunked async streaming pipeline for instant conversational flow.

---

## Architecture Overview

```
 [KDE Connect / Hotkey / HUD Click]
              │
              ▼
   [Ears: Faster-Whisper CPU]
              │
              ▼
   [Brain: Claude Haiku / Antigravity Session]
              │ (Streaming tokens)
              ▼
   [Sentence Chunker + Piper TTS Worker]
              │
              ▼
   [Voice: PipeWire Output + Reactive Hologram HUD]
```

See [docs/wayfinder/map.md](docs/wayfinder/map.md) for the complete decision and architecture specifications.

