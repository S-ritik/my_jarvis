"""The one typed settings object.

Knowledge owned here: every tunable, its built-in default (numbers straight from the
ADRs), the TOML layout of ``$XDG_CONFIG_HOME/jarvis/config.toml``, and validation.
Nothing else in JARVIS reads config files or environment variables for settings: the
composition root calls ``load_settings`` once and hands sub-objects to whoever needs
them (``Settings.listening`` to the Listener, ``Settings.safety`` to the Safety Gate, ...).

Durations are stored in milliseconds; the listening policy converts them to samples
once (``jarvis.audio.ms_to_samples``) so no policy reads a wall clock.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from jarvis.brain.port import BackendKind, BuiltinTool
from jarvis.core.vocabulary import AppEntry, CueEvent, Persona, PersonaName, VoiceId


class ConfigError(Exception):
    """Raised only by ``load_settings``; the daemon logs (and speaks, if Voice is up) every problem and refuses to start."""

    def __init__(self, problems: tuple[str, ...]) -> None:
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class XdgPaths:
    config_dir: Path
    data_dir: Path
    state_dir: Path
    runtime_dir: Path

    @staticmethod
    def from_environ(environ: Mapping[str, str], home: Path) -> XdgPaths:
        """The one place XDG variables are read (composition root only)."""
        raise NotImplementedError


@dataclass(frozen=True)
class Paths:
    xdg: XdgPaths
    models_dir: Path
    audit_log: Path
    turn_log: Path

    @property
    def runtime_dir(self) -> Path:
        return self.xdg.runtime_dir


@dataclass(frozen=True)
class AudioSettings:
    input_device: str | None = None
    """None = PipeWire default source."""
    output_device: str | None = None


@dataclass(frozen=True)
class ModelSettings:
    wake_model: Path = Path("hey_jarvis_v0.1.onnx")
    wake_vad_threshold: float = 0.5
    """OpenWakeWord's built-in VAD gating (ADR 03); applied inside the wake adapter."""
    silero_vad: Path = Path("silero_vad.onnx")
    whisper_model: str = "base.en"
    whisper_cpu_threads: int = 4
    whisper_beam_size: int = 1
    voices: Mapping[VoiceId, Path] = field(default_factory=dict)


@dataclass(frozen=True)
class ListeningSettings:
    """ADR 03 / ADR 04 / spec numbers. Consumed only by ``core.listening.Listener``."""

    wake_threshold: float = 0.65
    wake_consecutive_frames: int = 2
    wake_refractory_ms: int = 2_000
    preroll_ms: int = 500
    ack_window_ms: int = 400
    speech_onset_probability: float = 0.5
    silence_probability: float = 0.35
    flowing_after_voiced_ms: int = 1_000
    short_tier_silence_ms: int = 700
    flowing_tier_silence_ms: int = 480
    """Validated to lie within ADR 04's 450-500 ms."""
    ceiling_ms: int = 15_000
    no_speech_timeout_ms: int = 5_000
    playback_hangover_ms: int = 250


@dataclass(frozen=True)
class SpeechSettings:
    min_sentence_words: int = 4
    link_replacement: str = "a link"


@dataclass(frozen=True)
class CueSpec:
    pool: tuple[str, ...]
    """Clip paths relative to ``CueSettings.assets_root`` without extension, e.g. ``acolyte/AcolyteWhat1``."""
    fallback_line: str
    enabled: bool = True


@dataclass(frozen=True)
class CueSettings:
    assets_root: Path
    events: Mapping[CueEvent, CueSpec]
    """Always holds all six events (defaults below, overridden per key from TOML)."""


@dataclass(frozen=True)
class ClaudeSettings:
    cli_path: Path | None = None
    """None = the CLI bundled with claude-agent-sdk."""
    first_event_timeout_s: float = 20.0
    turn_timeout_s: float = 180.0


@dataclass(frozen=True)
class AntigravitySettings:
    command: str = "antigravity"
    first_event_timeout_s: float = 20.0
    turn_timeout_s: float = 180.0


@dataclass(frozen=True)
class BrainSettings:
    workspace: Path
    claude: ClaudeSettings = ClaudeSettings()
    antigravity: AntigravitySettings = AntigravitySettings()

    def timeouts(self, backend: BackendKind) -> tuple[float, float]:
        """(first_event_timeout_s, turn_timeout_s) for a backend."""
        raise NotImplementedError


@dataclass(frozen=True)
class SafetySettings:
    home: Path
    workspace_roots: tuple[Path, ...]
    protected_dirs: tuple[Path, ...] = (
        Path("/etc"), Path("/usr"), Path("/boot"), Path("/var"), Path("/lib"),
        Path("/bin"), Path("/sbin"), Path("/lib64"),
    )
    allowlist: frozenset[BuiltinTool] = frozenset(BuiltinTool)


@dataclass(frozen=True)
class MemorySettings:
    db_path: Path = Path("memory.db")
    search_limit: int = 5
    preamble_chars: int = 1_500


@dataclass(frozen=True)
class DesktopSettings:
    app_aliases: Mapping[str, AppEntry] = field(default_factory=dict)


@dataclass(frozen=True)
class ControlSettings:
    socket_name: str = "jarvis.sock"
    subscriber_queue: int = 256
    level_max_hz: float = 30.0
    max_line_bytes: int = 64 * 1024


@dataclass(frozen=True)
class LoggingSettings:
    log_transcripts: bool = True


@dataclass(frozen=True)
class Settings:
    paths: Paths
    audio: AudioSettings
    models: ModelSettings
    listening: ListeningSettings
    speech: SpeechSettings
    cues: CueSettings
    personas: tuple[Persona, ...]
    default_persona: PersonaName
    brain: BrainSettings
    safety: SafetySettings
    memory: MemorySettings
    desktop: DesktopSettings
    control: ControlSettings
    logging: LoggingSettings
    start_asleep: bool = False


DEFAULT_PERSONAS: tuple[Persona, ...] = (
    Persona(PersonaName("jarvis"), "Jarvis", ("jarvis",), BackendKind.CLAUDE_CODE, "haiku",
            VoiceId("en_GB-alan-medium"), "A loyal, sharp majordomo ..."),
    Persona(PersonaName("architect"), "Architect", ("architect",), BackendKind.CLAUDE_CODE, "sonnet",
            VoiceId("en_US-ryan-high"), "A deep engineering counsellor ..."),
    Persona(PersonaName("oracle"), "Oracle", ("oracle",), BackendKind.ANTIGRAVITY, "gemini-flash",
            VoiceId("en_US-lessac-medium"), "A far-seeing scout of the web ..."),
)
"""Custom personas come only from config ([personas.<name>] tables)."""

DEFAULT_CUES: Mapping[CueEvent, CueSpec] = {
    CueEvent.BOOT: CueSpec(("mech/defensive_systems_online",), "All defense systems online."),
    CueEvent.WAKE_ACK: CueSpec(tuple(f"acolyte/AcolyteWhat{i}" for i in range(1, 6)), "At your call."),
    CueEvent.TASK_RECEIVED: CueSpec(tuple(f"acolyte/AcolyteYes{i}" for i in range(1, 5)), "As my master wishes."),
    CueEvent.TASK_COMPLETED: CueSpec(("cues/jobs_done", "cues/work_complete"), "Job's done!"),
    CueEvent.SAFETY_BLOCKED: CueSpec((), "That would be… unwise."),
    CueEvent.SHUTDOWN: CueSpec((), "Powering down. My watch is ended."),
}


def default_settings(*, xdg: XdgPaths, home: Path) -> Settings:
    """Built-in defaults for a given home/XDG layout. ``load_settings`` starts from this;
    tests use it plus ``dataclasses.replace`` (one way to build a valid ``Settings``)."""
    raise NotImplementedError


def load_settings(config_file: Path | None, *, xdg: XdgPaths, home: Path) -> Settings:
    """Parse TOML with ``tomllib``, layer it over the defaults, validate, return ``Settings``.

    Raises ``ConfigError`` listing *every* problem (unknown keys, out-of-range numbers such
    as ``flowing_tier_silence_ms`` outside 450-500, personas with unknown backends,
    duplicate aliases, missing default persona, cue events with unknown names).
    """
    raise NotImplementedError
    # raw = tomllib.load(f) if config_file and config_file.exists() else {}
    # problems = []
    # listening = _section(raw, "listening", ListeningSettings, problems)
    # ... one _section per dataclass; personas merged by name over DEFAULT_PERSONAS
    # if problems: raise ConfigError(tuple(problems))
