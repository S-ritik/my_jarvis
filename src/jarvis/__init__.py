"""JARVIS v1: a local, voice-first desktop assistant daemon.

Package map (each line: the knowledge the package owns and hides):

- ``jarvis.audio``     audio value types (the one documented numpy alias) and sample/ms arithmetic
- ``jarvis.settings``  the one typed ``Settings`` object: TOML + built-in defaults + validation
- ``jarvis.core``      the Assistant Core (seam 1): turn state machine, every policy, the event stream
- ``jarvis.brain``     the Brain backend port and its Claude Code / Antigravity adapters
- ``jarvis.memory``    the SQLite FTS5 Memory Store and the ``save_memory``/``search_memory`` tools
- ``jarvis.control``   the Control Socket (seam 2): wire schema, server, ``jarvis ctl`` client
- ``jarvis.hud``       the HUD's client contract (rendering internals out of scope)
- ``jarvis.adapters``  hardware/OS adapters: the only modules importing sounddevice, onnx, piper, ...
- ``jarvis.daemon``    composition root
- ``jarvis.cli``       the ``jarvis`` command (run, ctl, hud, setup, doctor)
"""
