# Wake Word Engine Selection and Resource Profile

Type: research
Status: resolved
Blocked by: 02

## Question

Between OpenWakeWord (pre-trained "hey jarvis" / "alexa" models vs custom ONNX model) and Picovoice Porcupine (access-key required), which engine delivers reliable detection with sub-2% idle CPU utilization on an Intel i9-13th Gen without a GPU, and what is the exact setup procedure on Linux?

## Answer

- **Selected Engine**: **OpenWakeWord** (ONNX Runtime on CPU). Picovoice Porcupine is disqualified because its free tier was discontinued, and it mandates an active internet connection to validate access keys on engine initialization. OpenWakeWord is 100% offline, Apache 2.0, and has zero network dependencies.
- **Model**: Ships with an out-of-the-box pre-trained `"hey_jarvis"` model (`hey_jarvis_v0.1.onnx`), eliminating the need for custom synthetic training upfront.
- **CPU & Performance on i9-13900**: Each 80ms audio frame evaluates in ~0.55ms (~0.69% load on a single core, <0.04% total system CPU).
- **Critical Thread Optimization**: Set `os.environ["OMP_NUM_THREADS"] = "1"` to prevent ONNX Runtime from spinning up threads across all 20 logical cores, which causes latency spikes and power thrashing.
- **False-Positive Tuning**:
  1. Increase activation threshold from default `0.50` to `0.65`.
  2. Require 2 consecutive frames (160ms) exceeding threshold before triggering.
  3. Enforce a 2.0-second refractory lockout window (`model.reset()`).
  4. Enable integrated Silero VAD gating (`vad_threshold=0.5`) to bypass mechanical background noise (fans, typing).
