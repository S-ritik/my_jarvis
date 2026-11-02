# Personal AI Assistant (JARVIS) Implementation Map

## Destination

A complete architecture specification and resolved decision record for a voice-driven Linux desktop AI assistant running on an Intel i9-13th Gen laptop, combining local audio processing (OpenWakeWord, Faster-Whisper, Piper TTS) with cloud reasoning (Claude and Gemini APIs) and secure system automation. Reaching the end of this map means all architectural, authentication, latency, audio concurrency, and safety decisions are settled, leaving no open questions before code execution begins.

## Notes

- Domain: Linux Desktop Voice Agent / Human-Computer Interface
- Target Environment: Linux (Ubuntu/Debian-compatible, PipeWire/PulseAudio, Python 3.14, Intel Core i9-13900H/K CPU, no discrete GPU)
- Skills to consult: `research`, `grilling`, `prototype`, `domain-modeling`
- Standing preferences: 
  - Strictly local audio processing for wake word, STT, and TTS (zero voice data uploaded to third parties)
  - Latency-first architecture using sentence streaming to achieve under 1.5s time-to-first-spoken-token
  - Defense-in-depth safety checks preventing destructive shell actions without explicit user confirmation

## Decisions so far

<!-- the index: one line per closed ticket, enough to judge relevance, then zoom the link for the detail the ticket holds -->

- [[01: Subscription vs API Key Authentication Strategy](issues/01-auth-strategy.md)]: Zero paid APIs. Drive existing subscriptions via local session bridges (Claude Code CLI for Claude; Antigravity SDK/session for Gemini) with built-in tool execution.
- [[02: Linux Audio IO and Mic Concurrency Stack](issues/02-linux-audio-stack.md)]: Use `sounddevice` with decoupled streams over PipeWire default device (16kHz mono `int16` capture, on-demand playback, server-side resampling).
- [[03: Wake Word Engine Selection and Resource Profile](issues/03-wake-word-selection.md)]: Use OpenWakeWord with pre-trained `hey_jarvis_v0.1.onnx` on CPU (<0.05% system CPU with `OMP_NUM_THREADS=1`), threshold 0.65, 2-frame debounce, 100% offline.
- [[04: VAD Turn-Taking and Silence Detection Thresholds](issues/04-vad-turn-taking.md)]: Option C Adaptive Two-Tier Silero VAD (700ms silence for short phrase, 450-500ms for flowing speech, 15s hard ceiling).
- [[05: LLM Routing and Intent Dispatch Heuristic](issues/05-llm-routing-heuristic.md)]: Claude Haiku as default brain for low latency; 4-model personality matrix with paired TTS voices; persistent background REPL session per voice run with clean boot on restart; zero-latency bypass for simple OS tasks.
- [[06: Tool Execution Sandbox and Safety Confirmation Gate](issues/06-safety-sandbox.md)]: Strict zero-sudo sandbox (Option B). Hard denylist against `sudo`, root writes, and destructive disk commands; vocal rejection directing human to run manually in terminal.
- [[07: Sentence Chunked Streaming Pipeline](issues/07-sentence-streaming-pipeline.md)]: Decoupled async token-to-speech queue (LLM stream -> sentence regex -> Piper TTS -> sounddevice), starting playback at ~1.1s total turnaround with instant interrupt flushing.
- [[08: Local Context and Long Term Memory Store](issues/08-local-memory-store.md)]: Standard library `sqlite3` with FTS5 and WAL mode (<0.8ms BM25 search, 0 MB idle RAM, 0 dependencies) storing exact profile paths in relational tables and notes in FTS5 index.
- [[09: Hearthstone and Warcraft Flavor Dialogue Matrix](issues/09-flavor-soundboard-dialogues.md)]: Pre-rendered instant audio clips (<10ms) for lifecycle cues ("All defense systems online", "As my master wishes", "Job's done!") paired with a loyal majordomo persona for Claude Haiku.
- [[10: Holographic Sci-Fi Desktop HUD Overlay Engine](issues/10-holographic-desktop-hud.md)]: Lightweight native PyQt6 transparent vector HUD (<45 MB RAM, <0.8% CPU, 60fps) rendering glowing Arc Reactor rings with audio-reactive states (Idle, Listening, Thinking, Speaking).
- [[11: Semantic Soundboard Audio Router](issues/11-semantic-soundboard-router.md)]: Offline semantic soundboard router matching intents to pre-rendered voice clips using vector similarity with threshold gating, random selection for conversational variety, and deterministic fallback.

## Not yet specified

- Visual context and screen perception: screen capture triggers and piping desktop image frames to Gemini Flash vision.
- Ambient audio barge-in / interruption: acoustic echo cancellation (AEC) so user speech interrupts JARVIS while TTS audio is playing through speakers.
- Background asynchronous alert daemon: calendar reminders and timer alerts interrupting or queuing behind active voice turns.

## Out of scope

- Physical standalone 3D holographic hardware projectors (desktop transparent UI overlay is handled in ticket 10).
- Custom local LLM fine-tuning or running heavy 70B+ weights locally on CPU.
- Smart home / IoT protocol hubs (Zigbee, Matter, Home Assistant) until native OS laptop controls are fully stabilized.
- Exposing the assistant to incoming external network traffic or public webhooks.

