"""Verified output metadata and deterministic output discovery.

Discovery returns evidence-bearing candidates. It never turns an unfamiliar
natural-language phrase into an invented CarSim channel name.
"""
import csv
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from math import pi
from pathlib import Path

from carsim_errors import OutputChannelError
from discovery_query import DiscoveryQuery, ascii_query_terms, normalized_terms

VALID_OUTPUT_CATEGORIES = frozenset({
    "time", "vehicle_state", "wheel", "tire", "suspension", "steering",
    "brake", "powertrain", "driver", "road", "aero", "control",
    "environment", "other",
})


@dataclass(frozen=True)
class OutputSpec:
    """Unit and meaning metadata for a verified CarSim output channel."""

    name: str
    source_unit: str | None
    si_unit: str | None
    scale: float | None
    category: str
    description: str | None = None
    verified: bool = True
    source: str = "CarSim native run.csv"

    @property
    def native_unit(self) -> str | None:
        """P1 compatibility alias for ``source_unit``."""
        return self.source_unit


@dataclass(frozen=True)
class OutputCandidate:
    """One channel candidate with the evidence that produced it."""

    channel: str
    source: str
    matched_text: str
    reason: str
    verification_state: str
    spec: OutputSpec | None = None

    @property
    def name(self) -> str:
        """P2 compatibility alias."""
        return self.channel

    @property
    def evidence(self) -> str:
        """P2 compatibility alias."""
        return self.matched_text

    @property
    def confidence(self) -> str:
        """P2 compatibility alias."""
        return "verified" if self.verification_state == "registered" else "weak"


OUTPUT_REGISTRY: dict[str, OutputSpec] = {}


def _register(names: str, native: str, si: str, scale: float = 1.0,
              category: str = "other", description: str | None = None) -> None:
    if category not in VALID_OUTPUT_CATEGORIES:
        raise ValueError(f"Unknown output category: {category}")
    for name in names.split():
        OUTPUT_REGISTRY[name] = OutputSpec(
            name, native, si, scale, category, description)


_register("Time", "s", "s", category="time", description="simulation time")
_register("Vx Vy", "km/h", "m/s", 1 / 3.6, "vehicle_state", "vehicle velocity")
_register("Ax Ay", "g", "m/s^2", 9.80665, "vehicle_state", "vehicle acceleration")
_register("AVz", "deg/s", "rad/s", pi / 180, "vehicle_state", "vehicle yaw rate")
_register("Roll Pitch Yaw", "deg", "rad", pi / 180, "vehicle_state", "vehicle attitude")
_register("Xo Yo Zo", "m", "m", category="vehicle_state", description="vehicle position")
_register("Station", "m", "m", category="road", description="road station")
for _corner in ("L1", "R1", "L2", "R2"):
    _register("Vx_" + _corner, "km/h", "m/s", 1 / 3.6, "wheel", "wheel-center speed")
    _register("Steer_" + _corner, "deg", "rad", pi / 180, "steering", "road-wheel steer angle")
    _register("AVy_" + _corner, "rpm", "rad/s", 2 * pi / 60, "wheel", "wheel angular speed")
    _register("My_Dr_" + _corner, "N*m", "N*m", category="powertrain", description="drive torque")
    _register("My_Bk_" + _corner, "N*m", "N*m", category="brake", description="brake torque")
    _register(" ".join(p + _corner for p in ("Fx_", "Fy_", "Fz_")),
              "N", "N", category="tire", description="tire force")
    _register("Kappa_" + _corner, "1", "1", category="tire", description="tire longitudinal slip")
    _register("Alpha_" + _corner, "deg", "rad", pi / 180, "tire", "tire slip angle")
_register("AV_Mt_D1_L AV_Mt_D1_R AV_Mt_D2_L AV_Mt_D2_R",
          "rpm", "rad/s", 2 * pi / 60, "powertrain", "motor speed")

# Only aliases backed by existing field-verified registry entries belong here.
OUTPUT_ALIASES: dict[str, Sequence[str]] = {
    "yaw rate": ("AVz",),
    "vehicle speed": ("Vx",),
    "longitudinal vehicle speed": ("Vx",),
}

# These map physical descriptions to English physical search phrases, never to
# a CarSim channel. A literal channel still has to be found in an artifact.
OUTPUT_PHYSICAL_TERMS: dict[str, Sequence[str]] = {
    "前悬架垂向行程": ("front suspension travel", "front suspension vertical travel"),
    "方向盘转角": ("steering wheel angle",),
    "发动机转速": ("engine speed", "engine rpm"),
}

# WRT spellings differ from CSV spellings for these two known channels.
WRT_ALIASES = {"ROLL": "Roll", "PITCH": "Pitch"}
UNRELIABLE_COLS = ("Lat_Veh", "Lat_Targ")


def output_spec(name: str) -> OutputSpec:
    """Return verified metadata or fail closed when units are unknown."""
    canonical = WRT_ALIASES.get(name, name)
    try:
        return OUTPUT_REGISTRY[canonical]
    except KeyError:
        raise OutputChannelError(
            f"Unregistered channel {name!r}; discover and verify its native "
            "unit before adding it to OUTPUT_REGISTRY") from None


def resolve_output_alias(query: str) -> list[OutputSpec]:
    """Resolve an exact verified alias; unfamiliar text returns an empty list."""
    normalized = " ".join(str(query).casefold().split())
    if query in OUTPUT_REGISTRY or query in WRT_ALIASES:
        return [output_spec(query)]
    names = OUTPUT_ALIASES.get(normalized, ())
    return [output_spec(name) for name in names]


def normalize_output_query(
    query: str, search_terms: Iterable[str] | None = None
) -> DiscoveryQuery:
    """Normalize a multilingual query without mapping it to an invented channel."""
    original = " ".join(str(query).strip().split())
    aliases = tuple(spec.name for spec in resolve_output_alias(original))
    if search_terms is not None:
        terms = normalized_terms(search_terms)
    else:
        terms = normalized_terms(OUTPUT_PHYSICAL_TERMS.get(original, ()))
        if not terms:
            terms = ascii_query_terms(original)
    return DiscoveryQuery(original, terms, aliases)


def _source_files(sources: Iterable[str | Path]) -> Iterable[Path]:
    for source in sources:
        path = Path(source)
        if path.is_file():
            yield path
        elif path.is_dir():
            yield from (p for p in path.rglob("*") if p.is_file() and
                        p.suffix.lower() in {".csv", ".par", ".txt", ".sim"})


def find_output_candidates(
    query: str,
    sources: Iterable[str | Path] = (),
    limit: int = 50,
    *,
    search_terms: Iterable[str] | None = None,
    artifacts: Iterable[str | Path] | None = None,
) -> list[OutputCandidate]:
    """Find output candidates from verified aliases and supplied artifacts.

    Artifact discoveries are candidates, not verified facts. Callers must
    confirm native units in an echo/data definition before registration/use.
    """
    normalized = normalize_output_query(query, search_terms)
    if normalized.aliases:
        return [
            OutputCandidate(
                name,
                "verified registry",
                normalized.original,
                "exact verified alias or registered channel",
                "registered",
                output_spec(name),
            )
            for name in normalized.aliases
        ]
    if not normalized.search_terms:
        return []
    artifact_sources = tuple(sources) + tuple(artifacts or ())
    found: dict[str, OutputCandidate] = {}
    for path in _source_files(Path(p) for p in artifact_sources):
        try:
            if path.suffix.lower() == ".csv":
                with path.open("r", encoding="utf-8-sig", errors="ignore", newline="") as handle:
                    evidence_lines = [",".join(next(csv.reader(handle), []))]
            else:
                evidence_lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except OSError:
            continue
        for line in evidence_lines:
            folded = line.casefold()
            matched = next((term for term in normalized.search_terms if term in folded), None)
            if matched is None:
                continue
            tokens = re.findall(r"\b(?:WRT_)?[A-Za-z][A-Za-z0-9_]*\b", line)
            for token in tokens:
                name = token[4:] if token.upper().startswith("WRT_") else token
                canonical = WRT_ALIASES.get(name, name)
                spec = OUTPUT_REGISTRY.get(canonical)
                if spec is None and "_" not in name:
                    continue
                found.setdefault(
                    canonical,
                    OutputCandidate(
                        canonical,
                        str(path),
                        line.strip(),
                        f"literal artifact match for physical search term {matched!r}",
                        "registered" if spec else "artifact_match",
                        spec,
                    ),
                )
                if len(found) >= limit:
                    return list(found.values())
    return list(found.values())
