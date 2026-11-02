# 11: Semantic Soundboard Audio Router

**What to build:** An offline semantic soundboard router that dynamically selects pre-rendered voice clips by matching trigger intents against audio clip transcripts using vector similarity. Voice files are named after their spoken phrases (e.g. `jobs_done.wav`, `as_my_master_wishes.wav`). At startup or build time, embeddings are generated and cached for all audio clips. At runtime, when an intent or acknowledgment phrase occurs, the system computes cosine similarity against candidate clips, filters candidates above a configurable confidence threshold (e.g., `0.70`), and chooses randomly among qualifying clips to deliver natural conversational variety. If no candidate exceeds the threshold, it deterministically falls back to a designated default sound or standard TTS playback.

**Blocked by:** 09 (Hearthstone and Warcraft Flavor Dialogue Matrix), 02 (Linux Audio IO and Mic Concurrency Stack)

**Status:** ready-for-agent

- [ ] Filename-to-transcript extraction parser with support for optional intent alias metadata sidecars (`.json`).
- [ ] Offline local embedding pipeline using lightweight ONNX text embedding (`all-MiniLM-L6-v2`) caching vectors to a local SQLite or `.npz` store.
- [ ] Pre-computed vector lookup for canonical lifecycle events (Task Acknowledged, Task Completed, Safety Blocked) achieving <0.1ms vector match latency.
- [ ] Gated similarity selector: filters candidates with `cosine_similarity >= threshold`, picks randomly among qualifying matches with a 2-turn LRU history filter to prevent immediate repetition.
- [ ] Deterministic fallback mechanism: triggers default clip or TTS synthesis whenever max similarity < threshold.
- [ ] Voice pipeline integration (Issue #15): routes pre-rendered authentic clips for instant cues (<10ms) while normal generative AI messages use the low-latency generic Piper voice (~70ms).
- [ ] Verified by: `pytest tests/test_soundboard_router.py` verifying exact phrase match, semantic alias match, random distribution across threshold candidates, and graceful default fallback on low-similarity queries.
