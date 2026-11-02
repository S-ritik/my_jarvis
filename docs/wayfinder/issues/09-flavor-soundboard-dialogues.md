# Hearthstone and Warcraft Flavor Dialogue Matrix

Type: grilling
Status: resolved
Blocked by: none

## Question

Which specific Hearthstone and World of Warcraft voice lines and soundboard cues map to which assistant lifecycle events (Startup, Wake Word Trigger, Task Acknowledgment, Safety Rejection, Tool Completion, Shutdown)? Should common one-liners ("All defense systems online", "As my master wishes") be pre-synthesized audio clips played instantly at 0ms latency, or injected into Claude Haiku's system prompt to govern dynamic responses?

## Answer

- **Two-Tier Flavor Architecture**:
  1. **Tier 1: Pre-Rendered Instant Audio Clips (<10ms playback)**:
     Fixed lifecycle events bypass LLM generation and play pre-rendered audio files directly via `sounddevice` with zero conversational latency:
     - **Daemon Boot**: *"All defense systems online."* (Mimiron / Clockwork Mech)
     - **Wake Word Acknowledged**: *"At your call."* or *"Speak, mortal."* (Archmage / Medivh)
     - **Task Received**: *"As my master wishes."* (Acolyte / Cultist)
     - **Task Completed**: *"Job's done!"* (Classic Warcraft Peasant)
     - **Safety Gate Blocked**: *"That would be... unwise."* (Kel'Thuzad)
     - **Daemon Shutdown**: *"Powering down. My watch is ended."*
  2. **Tier 2: System Prompt Dynamic Persona**:
     For generative responses, Claude Haiku's system prompt is configured with a loyal, sharp, slightly grand fantasy-futuristic persona:
     - Speaks concisely and formally as a loyal high-tech majordomo.
     - Infuses subtle Warcraft/Hearthstone flavor ("It shall be done", "The elements obey", "Acknowledged, master") into tool status summaries without being bloated or annoying.
