# Sentence Chunked Streaming Pipeline

Type: prototype
Status: resolved
Blocked by: 01, 04

## Question

How should the asynchronous audio pipeline be designed to split streaming LLM text into punctuation-delimited sentence chunks and pipe them directly into Piper TTS playback concurrently, reducing time-to-first-spoken-word to under 1.2 seconds?

## Answer

- **Streaming Architecture**: Decoupled asynchronous token-to-speech pipeline.
  1. **Token Ingestion**: Background agent session (Claude Haiku / Antigravity) streams stdout tokens.
  2. **Sentence Chunker**: Buffers tokens and triggers an emit when encountering punctuation (`.`, `!`, `?`, `\n`) with a minimum 4-word safety guard (preventing premature breaks on abbreviations).
  3. **Concurrent Synthesis & Playback**: Sentence 1 text is queued to Piper TTS, which synthesizes 16-bit PCM in ~60–80ms on the Intel i9 CPU. `sounddevice` starts playing Sentence 1 audio through speakers at **~1.1–1.2s total turnaround**.
  4. **Pipelining**: While Sentence 1 is playing aloud, the agent completes Sentence 2 and Piper synthesizes Sentence 2, eliminating dead silence between sentences.
- **Pre-Cached Instant Audio Hooks**: Standard lifecycle cues (such as startup chimes or canned acknowledgments) bypass LLM inference entirely and play pre-rendered audio files instantly (<10ms).
- **Interruption & Flushes**: If the user speaks during playback, a signal immediately calls `sounddevice.stop()`, clears the audio frame queue, and resets the pipeline.
