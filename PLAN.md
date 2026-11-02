# JARVIS: Personal AI Assistant — Build Plan

## What you're building

A voice-driven AI assistant that runs on your laptop, listens for your commands, thinks using Claude and Gemini, speaks back to you, and can control your system. Think of it as a personal command center you talk to.

**Architecture overview:**

```
  🎤 You speak
      │
      ▼
  Wake Word (OpenWakeWord)        ← always listening, ~2-3% CPU
      │
      ▼
  Speech-to-Text (Faster-Whisper) ← local, no cloud
      │
      ▼
  Brain Router
      ├──► Claude API (complex reasoning)
      └──► Gemini API (multimodal, search)
              │
              ▼
        Tool Executor ──► System Actions (apps, files, terminal)
              │
              ▼
        Text-to-Speech (Piper TTS) ← local, <100ms
              │
              ▼
        🔊 JARVIS speaks
```

## Your hardware

| Component | Value | Impact |
|---|---|---|
| CPU | Intel i9 13th Gen | Excellent for CPU-based STT and TTS |
| GPU | None | No local LLM; use APIs instead |
| LLM access | Claude subscription + Gemini subscription | Best-in-class reasoning, no hardware limits |

The i9 13th gen has strong single-thread and multi-thread performance. Faster-Whisper's `base` model runs at near real-time on this CPU, and `small` runs at about 2-3x real-time. TTS with Piper is instant on CPU. The only latency you'll feel is the API round-trip to Claude or Gemini, which is typically 1-3 seconds.

---

## Architecture

### Layer 1: Ears (Speech-to-Text)

**Goal:** Convert your voice to text locally, fast and private.

| Option | Speed on i9 (no GPU) | Accuracy | Size |
|---|---|---|---|
| **Faster-Whisper `base.en`** (recommended to start) | ~real-time | Good for English | 150 MB |
| Faster-Whisper `small.en` | 2-3x real-time | Better | 500 MB |
| Faster-Whisper `medium.en` | 5-8x real-time | Great | 1.5 GB |
| Vosk (alternative) | Real-time streaming | Decent | 50 MB |

**Recommended:** Start with `Faster-Whisper base.en` for speed, upgrade to `small.en` once the pipeline works. Use VAD (Voice Activity Detection) via Silero to detect when you stop talking, so it only transcribes complete sentences.

**Key library:** `faster-whisper` (CTranslate2 backend, optimized for CPU)

### Layer 2: Wake Word (always-on listener)

**Goal:** The mic is always on, but the system only activates when you say "Jarvis" (or whatever trigger word you pick).

| Option | Accuracy | Customizable | Privacy |
|---|---|---|---|
| **OpenWakeWord** (recommended) | Good | Train custom words | Fully local |
| Porcupine (Picovoice) | Excellent | Pre-built + custom | Local, but needs free API key |
| Snowboy (archived) | Decent | Yes | Local |

**Recommended:** OpenWakeWord. It's fully open-source, runs a tiny model on CPU with negligible load, and you can train it to respond to "Jarvis" or any word you like.

**Flow:**
1. Mic streams audio continuously through OpenWakeWord (costs about 2-3% CPU).
2. On detection, a chime plays and the system starts recording.
3. Silero VAD detects end of speech.
4. The recording is sent to Faster-Whisper for transcription.

### Layer 3: Brain (LLM routing)

**Goal:** Route your request to the right LLM, with tool-use capabilities.

```
  User query + context
        │
        ▼
    Intent Router
    ├── Complex reasoning, code, analysis ──► Claude API
    ├── Web search, multimodal, quick facts ──► Gemini API
    └── Simple commands (open app, set timer) ──► Local handler (no LLM needed)
        │
        ▼
    Tool execution layer
```

**Router logic (start simple, refine later):**
- Default to Claude for most things (you're paying for it, and it's excellent at reasoning).
- Use Gemini when the query involves web search/grounding, image/video understanding, or when you want a second opinion.
- Skip the LLM entirely for simple commands: "open Firefox", "what time is it", "set a timer for 5 minutes".

**API setup:**
- Claude: Use the `anthropic` Python SDK with your API key. Use `claude-sonnet-4-20250514` for speed, `claude-opus-4-20250514` for complex tasks.
- Gemini: Use the `google-genai` Python SDK. Use `gemini-2.0-flash` for speed, `gemini-2.5-pro` for heavy tasks.

**System prompt for JARVIS:**
The system prompt defines the personality, available tools, and response format. It should instruct the LLM to:
- Respond concisely (spoken output should be short).
- Return structured tool calls when an action is needed.
- Maintain conversation context within a session.

### Layer 4: Hands (Tool Use and System Control)

**Goal:** Let JARVIS actually do things on your laptop.

Define tools as Python functions that the LLM can call. Both Claude and Gemini support function calling natively.

**Starter tool set:**

| Tool | What it does | Implementation |
|---|---|---|
| `run_command` | Execute a shell command | `subprocess.run()` with safety checks |
| `open_app` | Launch an application | `subprocess.Popen(['xdg-open', ...])` or direct binary |
| `search_web` | Google something | Gemini with grounding, or `googlesearch-python` |
| `read_file` | Read a file's contents | `pathlib.Path.read_text()` |
| `write_file` | Write or append to a file | `pathlib.Path.write_text()` |
| `clipboard_copy` | Copy text to clipboard | `xclip` or `xsel` |
| `clipboard_paste` | Read clipboard | `xclip -o` |
| `screenshot` | Take a screenshot | `PIL.ImageGrab` or `scrot` |
| `set_timer` | Set a countdown timer | `threading.Timer` or `schedule` |
| `system_info` | CPU, RAM, disk usage | `psutil` |
| `media_control` | Play, pause, volume | `playerctl` (Linux) |
| `notify` | Desktop notification | `notify-send` (Linux) |
| `weather` | Current weather | OpenWeatherMap API (free tier) |
| `calendar` | Read/create events | Google Calendar API |

**CAUTION:** `run_command` is powerful but dangerous. Add a confirmation step for destructive commands (anything with `rm`, `sudo`, `mkfs`, `dd`, or pipes to `/dev/`). Start with a whitelist of safe commands and expand it as you build trust.

### Layer 5: Voice (Text-to-Speech)

**Goal:** JARVIS talks back to you with a natural voice.

| Option | Quality | Speed on CPU | Voices |
|---|---|---|---|
| **Piper TTS** (recommended) | Very natural | Instant | 100+ voices, many languages |
| Edge TTS | Excellent (Microsoft) | Fast (needs network) | 300+ voices |
| Bark (Suno) | Most natural | Slow on CPU | Cloneable |
| Coqui TTS | Good | Moderate | Many |

**Recommended:** Piper TTS for local, instant responses. It runs in under 100ms on your i9 for a typical sentence. Use a deep male English voice for the JARVIS aesthetic (the `en_US-ryan-high` or `en_GB-alan-medium` voices work well).

**Fallback:** Edge TTS when you want higher quality and don't mind the network round-trip. It uses Microsoft's neural TTS and sounds excellent.

### Layer 6: Memory (context across sessions)

**Goal:** JARVIS remembers your preferences, past conversations, and key facts.

| Layer | What it stores | Tech |
|---|---|---|
| **Short-term** | Current conversation turns | In-memory list (Python) |
| **Long-term facts** | "My project is at /mnt/data_drive/trade", preferences | SQLite or JSON file |
| **Semantic search** | Past conversations, searchable by meaning | ChromaDB + sentence-transformers (CPU-friendly) |

**Start simple:** A JSON file for preferences and facts, an in-memory list for conversation history. Add ChromaDB later when you want "remember that thing I said last week about the Fyers API".

---

## Project Structure

```
jarvis/
├── main.py                  # Entry point, main loop
├── config.py                # API keys, model choices, voice settings
├── requirements.txt
│
├── ears/
│   ├── wake_word.py         # OpenWakeWord listener
│   ├── transcriber.py       # Faster-Whisper STT
│   └── vad.py               # Silero Voice Activity Detection
│
├── brain/
│   ├── router.py            # Routes to Claude, Gemini, or local
│   ├── claude_client.py     # Claude API wrapper
│   ├── gemini_client.py     # Gemini API wrapper
│   ├── prompts.py           # System prompts and personality
│   └── context.py           # Conversation history management
│
├── hands/
│   ├── tools.py             # Tool registry and definitions
│   ├── system_tools.py      # OS-level actions
│   ├── web_tools.py         # Search, weather, etc.
│   └── safety.py            # Command validation and confirmation
│
├── voice/
│   ├── tts.py               # Piper TTS wrapper
│   └── audio.py             # Audio playback (sounddevice)
│
├── memory/
│   ├── short_term.py        # In-session context
│   ├── long_term.py         # Persistent facts (SQLite/JSON)
│   └── search.py            # Semantic search (ChromaDB, add later)
│
├── ui/                      # Optional: visual interface
│   ├── tray.py              # System tray icon with status
│   └── overlay.py           # Optional floating overlay
│
└── assets/
    ├── wake_word_model/     # Trained "Jarvis" wake word
    ├── chime.wav            # Activation sound
    └── voices/              # Piper voice models
```

---

## Dependencies

```txt
# Core
faster-whisper          # Speech-to-text (CPU optimized)
openwakeword            # Wake word detection
silero-vad              # Voice activity detection (via torch)
piper-tts               # Text-to-speech
sounddevice             # Audio I/O
numpy                   # Audio processing

# LLM APIs
anthropic               # Claude
google-genai            # Gemini

# Tools
psutil                  # System info
Pillow                  # Screenshots
schedule                # Timers

# Memory (add later)
chromadb                # Vector store
sentence-transformers   # Embeddings

# UI (optional)
pystray                 # System tray
```

---

## Build Phases

### Phase 1: Prove the loop works (1-2 days)

Build the minimum pipeline: mic input, STT, send to Claude, get response, TTS output.

**Deliverables:**
- `transcriber.py`: Record audio, transcribe with Faster-Whisper
- `claude_client.py`: Send text to Claude, get response
- `tts.py`: Speak the response with Piper
- `main.py`: Glue them together in a loop

**Test:** You press Enter to start recording, speak, press Enter to stop, and JARVIS responds with voice. No wake word yet, no tools.

### Phase 2: Always listening (1 day)

Add the wake word and VAD so it's hands-free.

**Deliverables:**
- `wake_word.py`: Continuous listening with OpenWakeWord
- `vad.py`: Detect end of speech with Silero
- Activation chime

**Test:** Say "Jarvis, what's the time?" and it responds without touching the keyboard.

### Phase 3: Tool use (2-3 days)

Give JARVIS hands. Define tools as functions, wire them into Claude's and Gemini's function calling.

**Deliverables:**
- `tools.py`: Tool registry with JSON schema definitions
- `system_tools.py`: Open apps, run commands, clipboard, notifications
- `safety.py`: Command validation
- Update `claude_client.py` and `gemini_client.py` to handle tool calls

**Test:** "Jarvis, open Firefox." "Jarvis, how much disk space do I have?" "Jarvis, remind me in 10 minutes to check the deployment."

### Phase 4: Brain routing + Gemini (1 day)

Add the Gemini client and a router that picks the right model.

**Deliverables:**
- `gemini_client.py`: Gemini API with function calling
- `router.py`: Intent classification (simple keyword rules to start)

**Test:** "Jarvis, search for the latest Python 3.13 features" goes to Gemini with grounding. "Jarvis, explain this error" goes to Claude.

### Phase 5: Memory (1-2 days)

Add persistent memory so JARVIS remembers things across sessions.

**Deliverables:**
- `long_term.py`: SQLite store for facts and preferences
- `short_term.py`: Sliding window context management
- Tools: `remember_fact`, `recall_facts`

**Test:** "Jarvis, remember that my trading API key is stored in /home/ritik/.env". Next session: "Jarvis, where's my trading API key?"

### Phase 6: Polish and personality (ongoing)

- Custom system prompt for JARVIS personality
- Better voice selection and tuning
- System tray icon showing listening/thinking/speaking state
- Error recovery (network failures, API rate limits)
- Logging and conversation history

---

## Latency Budget

For a conversation to feel natural, the total response time should stay under 4 seconds.

| Step | Expected time | Notes |
|---|---|---|
| Wake word detection | <100ms | Tiny model, always running |
| VAD end-of-speech | 500ms silence threshold | Tunable |
| STT (Faster-Whisper base.en) | 0.5-1s | For a typical 3-5 second utterance |
| API round-trip (Claude/Gemini) | 1-3s | Depends on response length; use streaming |
| Tool execution | 0-2s | Depends on the tool |
| TTS (Piper) | <100ms | Very fast on CPU |
| **Total** | **~2-5s** | Acceptable for conversational feel |

**Key optimization:** Use streaming for both the LLM and TTS. Start speaking the first sentence while the LLM is still generating the rest. This cuts perceived latency roughly in half. Both the Anthropic and Google SDKs support streaming responses.

---

## Cost Estimate (monthly)

Assuming moderate daily use (30-50 queries per day):

| Service | Estimated cost | Notes |
|---|---|---|
| Claude API | Covered by subscription | If using claude.ai via the web; if API, ~$5-15/month |
| Gemini API | Free tier: 60 queries/min | More than enough for personal use |
| Everything else | $0 | All local, open-source |

**NOTE:** If you're using your Claude and Gemini **subscriptions** (not API keys), you have two options:
1. **Use the API anyway** with a separate API key. Claude's API has a free tier for light use, and Gemini's free tier is generous (15 RPM on 2.5 Pro, 30 RPM on 2.0 Flash).
2. **Use the official SDKs with your subscription.** Gemini offers API access bundled with Google One AI Premium. For Claude, the Anthropic API is separate from the claude.ai subscription. You may need an API key from console.anthropic.com (they give $5 free credit to start).

---

## Security Considerations

1. **API keys:** Store in environment variables or a `.env` file, never in code.
2. **Command execution:** Whitelist safe commands; require confirmation for anything destructive.
3. **Audio privacy:** All audio processing is local. Nothing is sent to the cloud except the transcribed text to Claude/Gemini.
4. **File access:** Restrict tool access to specific directories initially.

---

## What's realistic vs. what's not

### Fully doable now
- Voice conversations with memory
- Opening apps, running commands, managing files
- Web search and summarization
- Code assistance (explain errors, generate snippets)
- Timers, reminders, system info
- Reading and summarizing documents
- Controlling media playback

### Doable with more work
- Screen understanding ("what's on my screen right now?") via screenshots + Gemini Vision
- Email integration (Gmail API)
- Calendar management (Google Calendar API)
- Smart home control (Home Assistant API)
- Continuous learning from your habits

### Not practical yet
- Real-time holographic UI (obviously)
- Controlling physical hardware beyond your laptop
- Truly autonomous long-running agents (reliability is not there yet)
- Perfect voice cloning of a specific person in real-time

---

## Next step

When you're ready to build, start with **Phase 1**: the core loop of listen, think, speak. That's the foundation everything else builds on.

