"""Typed scenario configuration. All vehicle inputs use SI units.

Generic CarSim scenario layer: timing (SimulationConfig) and typed vehicle
parameter overrides (VehicleOverrides). Research-specific concepts (estimator
whitelists, sensors, experiments) live in the workflow layer, not here.
"""
import math
from dataclasses import dataclass, fields
from typing import Optional


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
