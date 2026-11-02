# VAD Turn-Taking and Silence Detection Thresholds

Type: prototype
Status: resolved
Blocked by: 02

## Question

What Voice Activity Detection (Silero VAD) confidence threshold and trailing silence window (300ms vs 500ms vs 700ms) minimizes perceived turnaround time without prematurely truncating the user when pausing naturally mid-thought?

## Answer

- **Selected Policy**: **Option C (Adaptive Two-Tier VAD Window)**.
- **VAD Engine**: Silero VAD running locally via ONNX Runtime on CPU, ingesting 16kHz mono `float32` audio chunks.
- **Turn-Taking Thresholds**:
  1. **Short Utterance (1–2 initial words)**: Waits **700ms** of silence before cutover. This prevents cutting off users who pause briefly after saying "Hey Jarvis" while formulating their request.
  2. **Flowing Speech (> 3 words)**: Cuts over at **450–500ms** of continuous silence once Silero speech probability drops below `0.35`. This provides responsive, natural turn-taking.
  3. **Hard Ceiling**: 15 seconds maximum recording window. Any utterance reaching 15 seconds is automatically cut and sent to Faster-Whisper to prevent runaway buffering in ambient noise environments.
- **Handoff to STT**: Upon silence cutover, audio buffer passes immediately to Faster-Whisper `base.en` running on CPU (processing ~1.5s of speech in ~300ms).
