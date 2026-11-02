# Tool Execution Sandbox and Safety Confirmation Gate

Type: grilling
Status: resolved
Blocked by: 05

## Question

What is the security boundary for shell commands and system tools executed by JARVIS on the laptop? Which tool classes execute automatically without confirmation (read files, open apps, system metrics), which actions demand explicit voice or interactive confirmation (deleting files, sudo, modifying git trees), and how is confirmation signaled over audio?

## Answer

- **Security Model**: **Strict Sandbox / Zero Sudo (Option B)**. Absolute hard boundary against destructive or root-level operations over voice.
- **Hard Denylist**:
  - Commands containing `sudo`, `su`, `doas`.
  - Destructive disk operations (`dd`, `mkfs`, `fdisk`, `parted`, partitioning tools).
  - Unconstrained file deletions (`rm -rf /`, `rm -rf ~`, or unconfirmed broad deletions outside build directories).
  - Modifications to system directories (`/etc`, `/usr`, `/boot`, `/var`, `/lib`).
- **Rejection & Spoken Alert**: Any command intercepted by the safety filter is blocked before execution. JARVIS speaks back over TTS: *"This action requires elevated permissions. Please run it manually in a terminal."*
- **Permitted Operations**:
  - System read operations (system specs, CPU/RAM stats via `psutil`, file inspection, git status/diff).
  - Workspace development actions (running tests, building projects, package installations in virtual environments).
  - Desktop control (launching applications, adjusting volume, controlling playback via `playerctl`).
