"""The Control Socket (seam 2): the daemon's only API ("backend API").

- ``protocol``  wire schema + codec (single source of truth; imports nothing from core)
- ``mapping``   domain <-> wire (the one place they meet)
- ``server``    ``ControlServer.serving``, ``InstanceLock``
- ``client``    ``ControlClient``, ``run_ctl`` (``jarvis ctl``)
"""
