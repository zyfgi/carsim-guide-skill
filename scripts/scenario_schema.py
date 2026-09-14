"""Typed scenario configuration. All vehicle inputs use SI units.

Generic CarSim scenario layer: timing (SimulationConfig), typed vehicle
parameter overrides (VehicleOverrides) and validation of generic scenario
YAML/JSON (validate_scenario / load_scenario against schemas/
scenario.schema.json). Research-specific concepts (estimator whitelists,
sensors, experiments) live in the workflow layer, not here.
"""
import json
import math
import re
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

from result_contract import channel


@dataclass(frozen=True)
class SimulationConfig:
    dt: float = 0.001
    duration: float = 30.0

    def __post_init__(self):
        if not all(math.isfinite(x) and x > 0 for x in (self.dt, self.duration)):
            raise ValueError("dt and duration must be finite and positive")
        steps = self.duration / self.dt
        if self.dt < 1e-7 or not math.isclose(steps, round(steps), abs_tol=1e-7, rel_tol=0):
            raise ValueError("duration must be an integral number of steps; dt >= 1e-7 s")


@dataclass(frozen=True)
class VehicleOverrides:
    sprung_mass_kg: Optional[float] = None
    cg_x_m: Optional[float] = None
    cg_y_m: Optional[float] = None
    cg_z_m: Optional[float] = None
    izz_kgm2: Optional[float] = None

    def __post_init__(self):
        for f in fields(self):
            value = getattr(self, f.name)
            if value is not None and not math.isfinite(value):
                raise ValueError("%s must be finite" % f.name)
        for name in ("sprung_mass_kg", "izz_kgm2"):
            value = getattr(self, name)
            if value is not None and value <= 0:
                raise ValueError("%s must be positive" % f.name)
        if self.cg_z_m is not None and self.cg_z_m < 0:
            raise ValueError("cg_z_m must be nonnegative")

    def keywords(self):
        mapping = {"sprung_mass_kg": ("M_SU", 1), "cg_x_m": ("LX_CG_SU", 1000),
                   "cg_y_m": ("Y_CG_SU", 1000), "cg_z_m": ("H_CG_SU", 1000),
                   "izz_kgm2": ("IZZ_SU", 1)}
        return {key: getattr(self, name) * factor for name, (key, factor) in mapping.items()
                if getattr(self, name) is not None}

    def lines(self):
        return ["%s %.12g" % item for item in self.keywords().items()]


def _validate_maneuver(config, sim):
    for key in ("speed_kmh", "steering_deg"):
        rows = config["maneuver"][key]
        times = [r[0] for r in rows]
        if times[0] != 0 or times[-1] > sim.duration or any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("%s times must start at zero, increase, and stay within duration" % key)
        if not all(math.isfinite(v) for row in rows for v in row):
            raise ValueError("Nonfinite maneuver value")


def validate_scenario(config):
    """Validate a generic scenario dict: schema + semantics. No research
    concepts exist here; every registered output channel (tire forces
    included) is a legal output."""
    import jsonschema
    schema = Path(__file__).resolve().parents[1] / "schemas" / "scenario.schema.json"
    jsonschema.Draft202012Validator(json.loads(schema.read_text(encoding="utf-8"))).validate(config)
    sim = SimulationConfig(**config["simulation"])
    VehicleOverrides(**config.get("vehicle", {}))
    for row in config.get("parameters", []):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", row["keyword"]):
            raise ValueError("Invalid parameter keyword: %r" % row["keyword"])
        if not math.isfinite(row["value"]):
            raise ValueError("Parameter value must be finite: %s" % row["keyword"])
    for name in config["outputs"]["channels"]:
        channel(name)  # unregistered units fail closed
        if name == "Time":
            raise ValueError("Time is written automatically; remove it from outputs.channels")
    _validate_maneuver(config, sim)
    if not math.isfinite(config["road"]["friction"]):
        raise ValueError("friction must be finite")
    threshold = config.get("validation", {}).get("minimum_speed_mps", 0)
    if not math.isfinite(threshold):
        raise ValueError("Movement threshold must be finite")
    return config


def load_scenario(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        value = json.loads(text)
    else:
        import yaml
        value = yaml.safe_load(text)
    return validate_scenario(value)
