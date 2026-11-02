# LLM Routing and Intent Dispatch Heuristic

Type: grilling
Status: resolved
Blocked by: 01

## Question

What deterministic vs classifier-based routing rules determine whether a user command bypasses LLMs completely (direct OS commands like volume or app launches), routes to Gemini Flash (web queries, multimodal, fast facts), or routes to Claude Sonnet/Opus (code tasks, multi-step problem solving)?

## Answer

- **Default Brain Model**: **Claude Haiku** (invoked via Claude Code with `--model haiku`). Chosen for sub-second conversational latency, concise voice-friendly responses, and low subscription resource drain.
- **4-Model Personality Matrix**: Support 4 distinct personas switchable on-the-fly via voice command ("Switch to Architect", "Switch to Oracle", etc.), each mapped to a specific model and Piper TTS voice profile:
  1. **Jarvis (Default / Butler)**: Powered by *Claude Haiku*. Concise, fast turnaround, everyday tasks, system control. Voice: British/formal (e.g. `en_GB-alan-medium`).
  2. **Architect (Deep Engineer)**: Powered by *Claude Sonnet / Opus*. Deep debugging, codebase architecture, complex scripting. Voice: Deeper male voice (e.g. `en_US-ryan-high`).
  3. **Oracle (Web & Visual Scout)**: Powered by *Gemini Flash* (via Antigravity). Web search, live documentation, screen inspection. Voice: Clear neutral voice (e.g. `en_US-lessac-medium`).
  4. **Custom Persona (Specialist)**: Configurable model/personality profile for user-defined tasks.
- **Session Lifecycle**: **Persistent background interactive session per voice run**. Context, working memory, and tool state persist continuously across back-and-forth turns while the assistant daemon is running. Exiting the daemon terminates the process; restarting initiates a clean, fresh session.
- **Zero-Latency Bypass**: Simple deterministic OS commands (e.g., volume control, media play/pause, current time, app launching) execute instantly in Python without waiting for agent round-trips.
