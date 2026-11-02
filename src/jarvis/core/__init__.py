"""The Assistant Core (seam 1).

Public entry points (import from the defining module; this package does not re-export,
to keep ``jarvis.settings`` -> ``jarvis.core.vocabulary`` import-cycle free):

- ``jarvis.core.assistant.AssistantCore``   the actor: ``async with``, ``command``, ``subscribe``, ``status``
- ``jarvis.core.ports.Ports`` and the port Protocols it bundles
- ``jarvis.core.vocabulary``                commands, routes, intents, events, status
- ``jarvis.core.bus.EventSubscription`` / ``Envelope`` / ``SubscriptionEnd``
- ``jarvis.core.phrases.SAFETY_LINE``       (tests assert on it)

Everything else in this package (listening, router, safety, speech, cues, personas,
prompt) is a policy or effect module used only by ``assistant.py``.
"""
