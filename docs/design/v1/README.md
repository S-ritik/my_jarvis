# JARVIS v1 — design scaffold and rationale

Design for the v1 spec ([S-ritik/my_jarvis#19](https://github.com/S-ritik/my_jarvis/issues/19)), produced with the `/architect` workflow (ground → sketch three candidates → screen → synthesize). **Design only:** every body under `src/jarvis/` is `raise NotImplementedError` plus pseudocode; signatures, types, module boundaries and contracts are the deliverable. The scaffold passes `mypy --strict` (40 modules) against the real `claude-agent-sdk` 0.2.176 and numpy.

Scope, as requested — "contract interfaces, backend API and indexer":

| Scope item | Where it lives |
|---|---|
| **Contract interfaces**: the Assistant Core (seam 1), every port it depends on, the domain vocabulary, and where each policy lives | `core/assistant.py`, `core/ports.py`, `core/vocabulary.py`, `core/{listening,router,safety,speech,cues,personas,prompt,phrases}.py`, `audio.py`, `settings.py` |
| **Backend API (a)**: the daemon's Control Socket (seam 2): wire schema, server, `jarvis ctl`, and the HUD client contract | `control/{protocol,mapping,server,client}.py`, `hud/link.py` |
| **Backend API (b)**: the Brain backend port, with Claude Code (Agent SDK) and Antigravity adapters | `brain/port.py`, `brain/claude.py`, `brain/antigravity.py` |
| **Indexer**: SQLite FTS5 Memory Store and the `save_memory` / `search_memory` Brain tools | `memory/store.py` (DDL, upsert, sanitized BM25 search, preamble), `memory/tools.py` |

Test-seam sketches are in `docs/design/v1/test-sketches/`. They are scenario sketches, not runnable tests yet, and are kept out of `tests/` so pytest does not collect them.

## 1. Shape in one sentence

**A single-inbox actor core.** One asyncio task owns all turn state and is the only writer of the ordered domain-event stream. It consults pure, sample-clocked policy objects in-line. Every slow effect (transcription, brain turn, synthesis, playback, desktop action) runs as a task tagged with its turn, and that task posts its result back to the inbox. Staleness is checked once, before dispatch, and one flush cancels everything. Around the core sit:
- vendor-neutral ports, including a Brain port whose *capabilities* the core enforces;
- a Control Socket whose wire schema lives in one module;
- a Memory Store that reaches the Brain only as a `BrainContext` (preamble plus tools), never through the core.

## 2. Usage sketch (caller code first; the types derive from it)

**(a) Composition root**: `jarvis run` → `cli.main` → `daemon.run_daemon`

```python
removed = harden_process(os.environ)        # billing vars gone + no_new_privs, before anything spawns
settings = load_settings(config_file, xdg=XdgPaths.from_environ(os.environ, Path.home()), home=Path.home())
with InstanceLock.acquire(settings.paths.runtime_dir, settings.control.socket_name):   # 2nd daemon -> exit 1
    memory = await MemoryStore.open(settings.memory.db_path, now=clock.now)            # FTS5 + WAL check
    ports = Ports(microphone=SoundDeviceMicrophone(...), wake=..., vad=..., transcriber=...,
                  brains={CLAUDE_CODE: ClaudeCodeBackend(settings.brain.claude),
                          ANTIGRAVITY: AntigravityBackend(settings.brain.antigravity)},
                  synthesizer=..., player=..., clips=..., desktop=LinuxDesktop(...),
                  context=MemoryContext(memory, settings.memory), audit=FileAuditLog(...),
                  clock=SystemClock(), rng=random.Random())
    core = AssistantCore(ports, settings)
    async with asyncio.TaskGroup() as tg, core, ControlServer.serving(core, lock, settings.control):
        tg.create_task(write_journal(core.subscribe(capacity=None), settings.logging, ...))
        await until_signalled(SIGINT, SIGTERM)
```

**(b) Core seam**: wake → speech → brain streams → safety deny

```python
brain = ScriptedBrain(turns=[[say("Clearing the logs now, master. "),
                              tool(RunShell("sudo rm -rf /var/log/journal")),
                              say("All done, the logs are gone. ")]])          # must never be heard
async with core_harness(tmp_path, brain=brain) as h:
    h.mic.feed(h.audio.silence(1.0), h.audio.wake(0.8, frames=2),
               h.audio.speech("clear the system logs", seconds=1.2), h.audio.silence(0.8))
    turn = await h.log.turn()
assert turn.first(SafetyRefused).category is DenyCategory.PRIVILEGE_ESCALATION
assert turn.after(SafetyRefused).spoken() == ["That would be… unwise.", SAFETY_LINE]
assert "All done" not in " ".join(turn.spoken()) and turn.outcome is TurnOutcome.REFUSED
```

**(c) Control Socket seam**: an `ask` turn observed by a subscriber

```python
async with socket_harness(tmp_path, brain=brain) as s, ControlClient(s.socket_path).subscribe() as feed:
    assert feed.hello.protocol == PROTOCOL_VERSION
    assert await run_ctl(["ask", "anything", "new?"], socket_path=s.socket_path, out=s.out, err=s.err) == 0
    messages = await feed.collect_until(TurnEndedEvent)
assert [m.seq for m in messages] == sorted(m.seq for m in messages)     # one total order
```

**(d) The Brain port**, as `core/personas.py` consumes it

```python
caps = backend.capabilities                                   # enforced HERE, not trusted to adapters
opened = await backend.open(SessionSpec(
    model=persona.model, system_prompt=compose_system_prompt(persona, await context.preamble()),
    builtins=settings.safety.allowlist if caps.gates_tools else frozenset(),
    tools=context.tools() if caps.custom_tools else (),
    gate=gate_for(persona.name), workspace=settings.brain.workspace))
async for event in opened.send("what's in my todo file?"):    # callable from any task (port rule 6)
    ...                                                       # TextDelta | ToolFinished | TurnEnded | BrainFailed
```

**(e) The indexer**, through the Brain tools

```python
context = MemoryContext(await MemoryStore.open(db, now=clock.now), MemorySettings(search_limit=5, preamble_chars=1500))
save, search = context.tools()
await save.handler({"type": "fact", "key": "paths.trade", "value": "/mnt/data_drive/trade"})
await save.handler({"type": "fact", "key": "Paths.Trade", "value": "/mnt/fast/trade"})        # upsert by normalized key
hits = await search.handler({"query": 'where\'s my "trading" project? AND OR *'})              # sanitized, never errors
assert "paths.trade: /mnt/fast/trade" in hits.text and "paths.trade" in await context.preamble()
```

## 3. Module map

```
src/jarvis/
  audio.py            16 kHz / 1280-sample frame facts, AudioFrame/Pcm aliases, ms<->samples. The only non-adapter numpy user.
  settings.py         One typed Settings (TOML + ADR defaults + validation). XDG/env read in one function.
  cli.py              jarvis run|ctl|hud|setup|doctor; OMP_NUM_THREADS=1 and harden_process() before any import/spawn.
  daemon.py           Composition root; harden_process (billing-var scrub + no_new_privs); per-turn journal.
  core/               SEAM 1 — the contract interfaces
    assistant.py      AssistantCore: the actor; transition/gating/cue-timing table; the single staleness check; the one flush.
    vocabulary.py     Closed unions: Command, Route, DesktopIntent, DomainEvent, Status, Persona, ids.
    ports.py          Every port Protocol the core depends on, plus the Ports bundle.
    bus.py            Ordered event stream: seq, fan-out, bounded queues, latest-wins levels, overflow, snapshot handshake.
    listening.py      Listener: wake debounce/refractory, pre-roll, ack window, two-tier endpoint, ceiling, timeout, hangover.
    router.py         Transcript normalization and ordered whole-utterance bypass grammar.
    safety.py         SafetyGate.check: shell-aware denylist. Pure.
    speech.py         Speech: chunker, speakable normalization, synth-ahead, cue rendering, Player item ids, flush.
    cues.py           CueBoard: preload, pools, enabled flags, fallback lines, seeded no-repeat choice.
    personas.py       Personas: table, availability, lazy sessions, capability enforcement, abandon, timeouts, crash restart.
    prompt.py         Five-part system prompt.        phrases.py  Every sentence JARVIS composes itself.
  brain/              BACKEND API (b)
    port.py           BrainBackend / BrainSession / BackendCapabilities / ToolCall / verdicts / events / errors. No vendor.
    claude.py         Agent SDK adapter: host task per session, PreToolUse gate bridge, stream reduction. Only SDK importer.
    antigravity.py    Probe-gated adapter; gates_tools=False and custom_tools=False until ticket 9.
  memory/             THE INDEXER
    store.py          MemoryStore: DDL, upsert, sanitized BM25 search, preamble. Only sqlite3 importer.
    tools.py          MemoryContext (a BrainContext): preamble budget plus save_memory/search_memory contracts.
  control/            BACKEND API (a) — seam 2
    protocol.py       Wire schema v1, codec and ctl argv grammar derived from one union. Imports nothing from core.
    mapping.py        Domain <-> wire, exhaustive; the only place the two vocabularies meet.
    server.py         ControlServer.serving (0600, SO_PEERCRED, framing, dispatch, subscriptions, overflow); InstanceLock.
    client.py         ControlClient (request/subscribe; NoDaemon as a value) and run_ctl (exit codes).
  hud/link.py         HUD contract: HudView reducer over wire messages, reconnecting watch(), send().
  adapters/*.py       One vendor per module: sounddevice_io, openwakeword_ears, whisper, piper, clips, desktop, system.
```

**Dependency direction:**
- `adapters` → `core.ports` / `brain.port`
- `core` → `brain.port`, `settings`, `audio`
- `memory` → `brain.port`
- `control.protocol` → nothing
- `control.mapping` / `control.server` → `core`
- `hud` → `control` only
- `daemon` → everything

The core never imports `memory`, `control`, `adapters` or a vendor.

## 4. Public surface

The package has 317 top-level public names across 40 modules (counted with `ast`). About 55% are closed data vocabularies: `core/vocabulary` 70, `control/protocol` 45, `brain/port` 35, `settings` 22 and `core/ports` 18. Every variant is a frozen dataclass, so `match` is exhaustive.

The behavioral entry points an agent must learn are few:

| Area | Entry points |
|---|---|
| Core (seam 1) | `AssistantCore(ports, settings)`, `async with`, `.command(cmd)`, `.subscribe(capacity=)`, `.status()` |
| Control (seam 2) | `InstanceLock.acquire`, `ControlServer.serving`, `ControlClient.request/.subscribe`, `run_ctl` |
| Brain port | `BrainBackend.kind/capabilities/probe/open`, `BrainSession.send/interrupt/close/interruptible` |
| Memory | `MemoryStore.open/save/search/preamble`, `MemoryContext.preamble/tools` |
| HUD | `apply`, `watch`, `send` |
| Settings | `load_settings`, `default_settings` |
| Process | `harden_process` |

## 5. Key decisions and rejected alternatives

**1. Actor core with a single inbox; not a "turn script", not a reducer.**
- *Why:* one task owns state and is the only publisher. Event order is therefore a total order by construction, and the primary seam can assert exact sequences.
- *Determinism* comes from three sources: listening time counted in samples, cue randomness from `Ports.rng`, and brain time from `Ports.clock`.
- *Rejected, structured-concurrency turn script* (candidate C): see the Synthesis decision.
- *Rejected, pure reducer plus interpreter:* every port call would exist twice, once as an `Effect` variant and once as an interpreter case. That amplifies changes on the most-copied path.

**2. Staleness is structural.** All turn-scoped inbox values carry a `TurnId`. `_handle` drops stale ones *before* dispatch, using one exhaustive function, `_turn_of`. A flush also *cancels* the turn's tasks, so the drop only covers results that were already queued. This is a graft (see §10).

**3. One flush; a safety deny abandons the brain turn.**
- `_flush_turn` is `speech.flush()` + `personas.abandon_turn()` + cancelling the turn's tasks.
- On a deny, the core publishes `SafetyRefused` and writes the audit entry. It then flushes speech and abandons the brain turn: native interrupt when the session supports it, otherwise drain and discard, and the session stays usable.
- Finally it plays `safety_blocked` and speaks the fixed line.
- Tool calls arriving from an abandoned turn get `Deny(TURN_CANCELLED)`. A stopped or refused turn can never go on running tools while the user hears nothing.
- *Rejected* (candidate A): mute the speech but let the brain turn continue.

**4. The Safety Gate is pure; its consequences are core policy.**
- The backend awaits `SessionSpec.gate` before *every* tool.
- The core's gate closure computes the verdict synchronously, posts `_GateIn` and returns. Any text the brain streamed before the call is already ahead of it in the inbox.
- For Claude, the gate runs on a `PreToolUse` hook with `matcher=None`, with `can_use_tool` as a backstop and `allowed_tools=[]`. Pre-approved calls skip `can_use_tool`, as the SDK 0.2.176 source shows.

**5. Capabilities are enforced by the caller.** `BackendCapabilities(gates_tools, custom_tools)` is read by `Personas`:
- an ungated backend is opened with **no built-ins**;
- a backend without custom-tool support gets no custom tools, and the preamble still applies.

Zero-sudo therefore doesn't depend on every future adapter author remembering the rule. This is a graft (see §10).

**6. Sessions may be driven from any task (port rule 6).** `ClaudeSDKClient` must be used in the async context that connected it, per the SDK's own caveat. The Claude adapter therefore hosts each session in one long-lived task and bridges to it with queues. The core's per-turn pump tasks never touch the client. This is a graft (see §10).

**7. Process hardening is daemon-wide.**
- `harden_process` deletes the billing variables (`ANTHROPIC_API_KEY` and others) from the daemon's own environment and sets `no_new_privs` on the daemon.
- The SDK builds the CLI env as `{**os.environ, **options.env}` and cannot remove a variable, so the daemon's environment is the only place to scrub it.
- Every brain process tree inherits both settings. Desktop apps escape `no_new_privs` because they launch through the user session manager.
- *Rejected* (candidate B's original): an exec-wrapper launcher passed as `cli_path`. It adds a module, a generated script and an SDK version probe that runs through the wrapper, and it must be re-applied to every new backend.

**8. Memory reaches the Brain only through `BrainContext`.**
- `MemoryContext` gives each *new* session the preamble and the two tools.
- The core never calls the store, so there is no pass-through.
- `store.py` is the only file that spells SQL.

**9. Indexer schema.**
- One FTS5 table, `search_index(kind UNINDEXED, key, body)` with `porter unicode61`, fed by triggers from `facts` and `snippets`.
- `rowid` encodes the source as 2·id (fact) or 2·id+1 (snippet), so triggers update by rowid.
- `facts.revision` is a global write counter that gives a deterministic, clock-free recency order for the preamble.
- BM25 weights are `(0, 2, 1)`: key hits rank above body hits.
- The sanitizer extracts `\w+` tokens, removes stopwords, quotes each token and joins them with **OR**. Voice queries are sentences, so AND would return nothing.

**10. One schema module for the wire.** `protocol.py` defines the schema, and decode, encode and `jarvis ctl` parsing are all derived from the `CommandBody` union. `mapping.py` is the one exhaustive domain↔wire translation. The HUD imports only `protocol` and `client`.

**11. Speech is one deep module**: chunker, normalization, synth-ahead, cue rendering, item ids and flush together. *Rejected:* separate chunker, synthesis-queue and playback-queue modules (temporal decomposition, with flush orchestrated across three objects).

**12. Errors are values at every port**: `BrainFailed`, `BrainError`, `ActionFailed`, `NoDaemon`, and `None` for a missing clip. Only boot-fatal conditions raise.

**13. The 250 ms hangover is a mic gate, not a state.**
- `TurnFinished` and `StateChanged(IDLE)` are published when playback drains, and the Listener then discards the next 250 ms of samples.
- This is identical for wake and endpointing, and a turn can still finish while no audio flows (`ask`, or while Asleep).
- Two of the three runners independently chose this reading of "Idle after hangover".

**Pressure points from grounding §4, resolved:**

| Pressure point | Resolved by |
|---|---|
| Core shape | Decision 1 |
| Where async lives / atomic flush | Decisions 2 and 3 |
| Safety Gate placement | Decision 4 |
| Memory tools without a pass-through | Decision 8 |
| Control Socket mapping | Decision 10 |
| Persona/session registry | `Personas` plus decisions 5 and 6 |
| Settings | One `Settings`, sub-objects passed at construction |

## 6. Red-flag screen (merged design)

| # | Flag | Verdict | Notes |
|---|---|---|---|
| 1 | Shallow module | RISK | `Listener` (5 methods) and `Speech` (6 calls) are internal, with the actor as their only caller. Every other entry point is deep. |
| 2 | Pass-through | PASS | No memory pass-through. `MemoryContext.preamble` adds the budget. |
| 3 | Information leakage | PASS | Wire names only in `protocol.py`, SQL only in `store.py`, SDK types and Claude tool names only in `claude.py`, phrasing only in `phrases.py`. |
| 4 | Temporal decomposition | PASS | Modules are split by knowledge. The "when" table lives in `assistant.py` only. |
| 5 | Callers must know ordering | RISK→mitigated | Port turn rules have one caller (`Personas`). Task affinity is now the adapter's problem (rule 6), not the caller's. |
| 6 | Multiple sources of truth | RISK | `Speech` slots versus the Player's device queue, guarded by item ids and generations. Add one flush-under-load adapter smoke test. |
| 7 | Stringly-typed | PASS | Closed unions everywhere. Wire `cue` and `outcome` stay open strings on purpose, for additive evolution. |
| 8 | Escape hatches | PASS | `Any` only inside `claude.py` (SDK dicts). |
| 9 | Boolean flag params | PASS | `BackendCapabilities` booleans are data read once, not mode switches on a call. |
| 10 | Wide surface | RISK | 317 names, mostly closed data. Behavioral entry points are listed in §4. |
| 11 | Untestable time / globals | PASS | Samples, `Clock`, `rng`. Env is read only in `cli` / `XdgPaths` / `harden_process`. |
| 12 | Vendor types across ports | PASS | Verified by `mypy --strict` against the real SDK. |
| 13 | Sync/async mismatch | RISK | Scorer `reset` and Player `enqueue`/`flush` are sync by contract (non-blocking hand-off). Documented in `ports.py`. |
| 14 | Exceptions as control flow | PASS | Errors are values (decision 12). |
| 15 | Seam bypass | PASS | §7 maps every item. |
| 16 | Config smeared | PASS | One `Settings`. |
| 17 | Nearest-example trap | RISK→reduced | Staleness and capability rules are now structural, so copying a handler or an adapter can't skip them. Remaining trap: a handler `await`ing a slow port in-line. `_spawn` is the documented only route. |

## 7. Seam mapping

**Seam 1 (Assistant Core)**, observed through the event log and process-edge fakes:

| Spec testing decision | Observed through |
|---|---|
| Wake threshold, two-frame debounce, refractory | `WakeDetected` or its absence |
| Wake-ack rule and pre-roll | `CuePlayed(WAKE_ACK)`; `Transcribed.raw` |
| Endpoint tiers, ceiling, no-speech timeout | `Transcribed`, `CaptureEnded.end`, `TurnFinished(NO_SPEECH)` |
| Mic gating and hangover | No `WakeDetected` during or within 250 ms of playback |
| Wake-phrase stripping, dismissals | `Transcribed.text`, `TurnFinished(DISMISSED)` |
| Bypass routing | `Routed`, `ActionPerformed`, fake desktop calls |
| Persona switching | `PersonaChanged`, `SentenceQueued.voice`, `SessionStarted`, `ScriptedBrain.specs` |
| Capability enforcement | `specs[-1].builtins/tools`, see `test_ungated_backend_is_opened_without_tools` |
| Chunking | `SentenceQueued.text` |
| Safety table | `verdicts`, `SafetyRefused`, cue plus `SAFETY_LINE`, no later speech, audit entries |
| Memory | Tool outputs; `specs[-1].system_prompt` |
| Interruption | `TurnFinished(INTERRUPTED)`, `brain.interrupts`, drain path |
| Sleep | `SleepChanged`, mic closed, `Rejected(ASLEEP)` |
| Cues | `CuePlayed` sequences with a seeded `Random` |
| Errors | `ErrorOccurred`, `SessionStarted(context_lost=True)` |

**Seam 2 (Control Socket):**
- every command's reply and its event effect;
- the ordering of an `ask` turn;
- several subscribers seeing identical `seq` order;
- malformed input rejected while the server keeps serving;
- socket mode 0600;
- `jarvis ctl` with no daemon exits 1 within 1 s;
- a second instance is refused.

## 8. Change scenarios

| Change | Files | Would an agent seeing one file get it right? |
|---|---|---|
| New bypass action intent | `vocabulary.py`, `router.py`, `adapters/desktop.py`, `control/mapping.py` (4) | Yes. `assert_never` flags the adapter and the mapping. |
| New Brain backend | new `brain/<x>.py`, `BackendKind`, its settings, one line in `daemon.py` (4) | Yes, and safer than before: forgetting the gate still yields no shell (decision 5), the process is already hardened (decision 7), and task affinity is stated in the port (decision 6). |
| New lifecycle cue | `CueEvent`, `DEFAULT_CUES`, one `speech.cue(...)` call site (3) | Mostly. `load_settings` validation catches a missing default. |
| New control command | `protocol.py`, `vocabulary.py`, `mapping.py`, `assistant.py` (4) | Yes. Three exhaustive matches; ctl parsing is derived. |
| New turn-tagged inbox input | `assistant.py` (the type, `_Input`, `_turn_of`) | Yes. `_turn_of` is exhaustive, so its turn scoping must be decided. |
| Change FTS ranking | `memory/store.py` (1) | Yes. |

## 9. Risks and open questions (to resolve in the first tickets)

1. **Claude gate path on the real CLI.**
   - Does `PreToolUse` with `matcher=None` fire for every built-in *and* for the SDK-MCP tools?
   - Does a hook deny reach the model as the tool result?
   - Is each parallel tool call gated?
2. **Daemon-wide `no_new_privs`.** Confirm nothing JARVIS runs needs setuid, and that `systemd-run --user` app launches don't inherit it.
3. **Virtual-time tests.** The seam-1 sketches assume a virtual-time loop (for example `looptime`).
   - The real `MemoryStore` uses worker threads, so memory scenarios must wait on events, not elapsed time.
   - Seam-2 tests run on real time; their only slow cases are the sub-1 s `ctl` timeouts.
   - Spike this in ticket 1. The fallback is anyio's `wait_all_tasks_blocked` (anyio already comes in with the SDK).
4. **Per-frame scoring runs in the actor.** If wake or VAD inference ever exceeds 80 ms, frames queue up. Log overruns, and move scoring into the mic pump if needed.
5. **Antigravity** has no confirmed headless surface. Oracle stays `Unavailable`, or tool-less if probed OK but ungated, until ticket 9.
6. **Spec readings to confirm:**
   - the hangover as a gate (decision 13);
   - `ask` allowed while Asleep, while `talk` is rejected;
   - a persona switch speaking a one-line acknowledgment in the new voice;
   - an `OUTSIDE_ALLOWLIST` deny speaking the same elevated-permissions line.
7. **AF_UNIX path length (107 bytes):** test runtime dirs must be short paths.
8. **Unused imports in stubs** (ruff F401, 23 occurrences) are intentional. They record each module's intended dependencies and disappear as bodies are filled.

## 10. Synthesis decision

**Candidates.** Three runners worked independently from the same grounding (`grounding.md`, the spec, and the real SDK/Piper/Whisper/OpenWakeWord sources):

| | A: runner-sonnet | B: runner-opus | C: runner-contrarian |
|---|---|---|---|
| Shape | Single-writer inbox actor + `policies/` package | Single-inbox actor, policies inside `core/` | Structured-concurrency "turn script": one async function per Turn in an anyio cancel scope, no inbox |
| Event order | Total, by construction | Total, by construction | Total but scheduler-dependent; tests assert causal subsequences |
| Deny | Mutes speech, brain turn continues | Flush: brain turn abandoned | Cancels the speech-line scope; exchange drained |
| Errors | Brain errors as events, other ports raise `PortError` | Values everywhere | Values everywhere |
| Claude task affinity | Not handled | Not handled | Host task per session (found the SDK caveat) |
| Hardening | `setpriv` wrapper via `cli_path` | Exec launcher via `cli_path` | Daemon-wide, at startup |
| Capabilities | `honors_guard` / `custom_tools`, enforced by the hub | Rule in a docstring; adapter enforces | `gates_tools`, enforced by the registry |
| Concurrency extras | — | Virtual-time tests | One `anyio.Lock`; cancellation conventions; anyio dependency |

A and B converged on the same shape, so per the skill a third runner was told to reject it. C is a genuine structural alternative.

**Base: B.** Why B over A, given they share a shape:
- Its safety deny abandons the brain turn instead of only muting it.
- It uses errors-as-values at every port instead of a cross-boundary `PortError`.
- It has fewer, deeper modules: `Speech` and `Personas` versus A's `SpeechOutput` + `BrainHub` + `TurnBag` + separate `policies/`.
- Its memory contract (`BrainContext`) is cleaner.
- Its `protocol.py` *derives* `ctl` parsing from the command union.

Why the actor shape over C:
1. It gives a total event order by construction. The primary seam can assert exact sequences, which the spec's "one ordered stream" and its test plan lean on, while C needs causal-subsequence assertions.
2. It has no locks. C needs a transition lock that every new transition must remember.
3. It avoids cancellation's sharp edges as the everyday contributor surface. In C, a missing shield on an `await` in a `finally`, or an emit from cancelled code, fails silently — exactly the nearest-example trap for an agent contributor.

C's readability advantage is real. The cost is that its correctness conventions are invisible.

**Grafts:**

| From | What | Why |
|---|---|---|
| C | **Host task per Claude session**, and port rule 6 ("a session may be driven from any task") | C was the only runner to catch the SDK's task-affinity caveat. B's per-turn pump tasks would have used a `ClaudeSDKClient` from a task other than the one that connected it. |
| C | **Daemon-wide `harden_process`** replaces B's `brain/launcher.py` | Subtracts a module and the generated wrapper script, removes the risk of the SDK's CLI version probe running through a wrapper, and covers every future backend for free. |
| C's critique | **Structural staleness** (`_turn_of` + one check in `_handle`) replaces B's per-handler "stale → drop" | C's strongest argument against the actor shape was that filtering is opt-in. Now it isn't. |
| A + C | **`BackendCapabilities` enforced by `Personas`** | In B, "don't enable a tool you can't gate" was a docstring rule each adapter had to honor. Now an ungated backend structurally gets no shell. |
| A | **Sanitizer and preamble choices** | OR semantics, stopwords, key-weighted BM25. B already matched A here; A confirmed it independently. |

**Not grafted:**
- A's `Microphone.open(sink)`: B's pump task is equivalent, and Asleep is observable either way.
- A's `policies/` package split: it would move the core's single-caller helpers away from their caller.
- C's anyio dependency and cancel scopes.

Runner outputs and grounding are kept outside the repo; this document records what was taken from each.
