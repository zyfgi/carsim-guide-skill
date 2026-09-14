"""Typed research configuration. All vehicle inputs use SI units."""
import json
import math
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Optional

from result_contract import CHANNEL_REGISTRY, channel


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
                raise ValueError("%s must be positive" % name)
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


def validate_experiment(config):
    import jsonschema
    schema = Path(__file__).resolve().parents[1] / "schemas" / "experiment.schema.json"
    jsonschema.Draft202012Validator(json.loads(schema.read_text(encoding="utf-8"))).validate(config)
    sim = SimulationConfig(**config["simulation"])
    VehicleOverrides(**config.get("vehicle_parameters", {}))
    # Schema-level check via core registry metadata only; the enforcing
    # privileged policy (GroundTruthLeakageError) lives in the workflow layer.
    privileged = [n for n in config["outputs"]["estimator"]
                  if channel(n).role == "truth"]
    if privileged:
        raise ValueError(
            "Estimator outputs cannot include privileged truth-role channels: %s"
            % privileged)
    for name in config["outputs"]["evaluator"]:
        channel(name)
    for name in config["outputs"]["estimator"] + config["outputs"]["evaluator"]:
        if name not in CHANNEL_REGISTRY or name == "Time":
            raise ValueError("Outputs must use canonical CSV signal names; Time is automatic")
    if not config["outputs"]["estimator"]:
        raise ValueError("At least one estimator channel is required")
    for key in ("speed_kmh", "steering_deg"):
        rows = config["maneuver"][key]
        times = [r[0] for r in rows]
        if times[0] != 0 or times[-1] > sim.duration or any(b <= a for a, b in zip(times, times[1:])):
            raise ValueError("%s times must start at zero, increase, and stay within duration" % key)
        if not all(math.isfinite(v) for row in rows for v in row):
            raise ValueError("Nonfinite maneuver value")
    if not math.isfinite(config["road"]["mu"]):
        raise ValueError("mu must be finite")
    threshold = config.get("validation", {}).get("minimum_speed_mps", 0)
    if not math.isfinite(threshold):
        raise ValueError("Movement threshold must be finite")
    if config.get("sensors"):
        from sensor_replay import SensorConfig
        covered = []
        for spec in config["sensors"].values():
            SensorConfig(**spec)
            covered.extend(spec["channels"])
            if spec["sample_hz"] > 1 / sim.dt:
                raise ValueError("Sensor rate exceeds solver rate")
        if len(covered) != len(set(covered)) or set(covered) != set(config["outputs"]["estimator"]):
            raise ValueError("Sensors must cover each estimator channel exactly once")
    return config


def load_experiment(path):
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        value = json.loads(text)
    else:
        import yaml
        value = yaml.safe_load(text)
    return validate_experiment(value)
