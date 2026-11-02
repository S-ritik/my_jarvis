"""The ``jarvis`` command: ``run``, ``ctl``, ``hud``, ``setup``, ``doctor``.

The only place (with ``settings.XdgPaths.from_environ``) that reads the process
environment. Sets ``OMP_NUM_THREADS=1`` before any ONNX Runtime import (ADR 03).
"""

from __future__ import annotations

from collections.abc import Sequence


def main(argv: Sequence[str] | None = None) -> int:
    raise NotImplementedError
    # os.environ.setdefault("OMP_NUM_THREADS", "1")   # before importing adapters
    # sub = argv[0]
    # run    -> harden_process(os.environ)               # billing vars removed + no_new_privs, first
    #           asyncio.run(run_daemon(load_settings(...)))
    # ctl    -> asyncio.run(run_ctl(argv[1:], socket_path=xdg.runtime_dir / "jarvis.sock", out=stdout, err=stderr))
    #           (no settings load: ctl must fail fast even with a broken config)
    # hud    -> jarvis.hud window (PyQt6) over hud.link.watch
    # setup  -> download models (the only network use)
    # doctor -> python version, FTS5, devices, models, ClaudeCodeBackend.probe(), AntigravityBackend.probe(),
    #           config validity, socket/lock state; each failure with a fix
