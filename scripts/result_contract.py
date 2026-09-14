"""Core channel registry: native CarSim CSV units, SI conversion, categories.

Core describes only what a CarSim output variable IS: its native unit, SI
unit, conversion factor, category and source. Unknown names fail closed
instead of being scaled by a guess. Nothing estimator-related lives here:
the privileged-channel policy is owned by the optional research workflow
(scripts/workflows/estimator_validation.py) and is never consulted by core
readers such as carsim_batch.read_run_csv().
"""
from dataclasses import dataclass
from math import pi


@dataclass(frozen=True)
class Channel:
    source_unit: str
    si_unit: str
    scale: float
    category: str = "other"   # core taxonomy: vehicle_state / wheel / tire / ...
    source: str = "CarSim native run.csv"


CHANNEL_REGISTRY = {}


def _register(names, native, si, scale=1.0, category="other"):
    for name in names.split():
        CHANNEL_REGISTRY[name] = Channel(native, si, scale, category)


_register("Time", "s", "s", category="time")
_register("Vx Vy", "km/h", "m/s", 1 / 3.6, category="vehicle_state")
_register("Ax Ay", "g", "m/s^2", 9.80665, category="vehicle_state")
_register("AVz", "deg/s", "rad/s", pi / 180, category="vehicle_state")
_register("Roll Pitch Yaw", "deg", "rad", pi / 180, category="vehicle_state")
_register("Xo Yo Zo", "m", "m", category="vehicle_state")
_register("Station", "m", "m", category="road")
for corner in ("L1", "R1", "L2", "R2"):
    _register("Vx_" + corner, "km/h", "m/s", 1 / 3.6, category="wheel")
    _register("Steer_" + corner, "deg", "rad", pi / 180, category="steering")
    _register("AVy_" + corner, "rpm", "rad/s", 2 * pi / 60, category="wheel")
    _register("My_Dr_" + corner, "N*m", "N*m", category="powertrain")
    _register("My_Bk_" + corner, "N*m", "N*m", category="control")
    _register(" ".join(p + corner for p in ("Fx_", "Fy_", "Fz_")),
              "N", "N", category="tire")
    _register("Kappa_" + corner, "1", "1", category="tire")
    _register("Alpha_" + corner, "deg", "rad", pi / 180, category="tire")
_register("AV_Mt_D1_L AV_Mt_D1_R AV_Mt_D2_L AV_Mt_D2_R",
          "rpm", "rad/s", 2 * pi / 60, category="powertrain")

# WRT keyword spellings differ from CSV header spellings for these two angles.
OUTPUT_ALIASES = {"ROLL": "Roll", "PITCH": "Pitch"}
UNRELIABLE_COLS = ("Lat_Veh", "Lat_Targ")


def channel(name):
    canonical = OUTPUT_ALIASES.get(name, name)
    try:
        return CHANNEL_REGISTRY[canonical]
    except KeyError:
        raise ValueError(
            "Unregistered channel %r; check its native unit (CarSim manual or "
            "run_echo.par) and register it in CHANNEL_REGISTRY before reading"
            % name) from None
