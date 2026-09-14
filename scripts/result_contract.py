"""Core channel registry: native CarSim CSV units, SI conversion, categories.

Every channel any core reader accepts must be registered here with its native
unit and conversion factor; unknown names fail closed instead of being scaled
by a guess. ``role`` marks which optional research workflows treat a channel
as privileged simulator output (estimator isolation) - it is never consulted
by core readers such as carsim_batch.read_run_csv().
"""
from dataclasses import asdict, dataclass
from math import pi

import pandas as pd


class GroundTruthLeakageError(ValueError):
    """Raised only by workflow-level views (estimator_view / sensor replay)
    when a channel the workflow marked privileged reaches the estimator."""


@dataclass(frozen=True)
class Channel:
    source_unit: str
    si_unit: str
    scale: float
    role: str          # workflow-layer marking: "observable" / "truth" / "time"
    category: str = "other"   # core taxonomy: vehicle_state / wheel / tire / ...
    source: str = "CarSim native run.csv"


CHANNEL_REGISTRY = {}


def _register(names, native, si, scale=1.0, role="observable", category="other"):
    for name in names.split():
        CHANNEL_REGISTRY[name] = Channel(native, si, scale, role, category)


_register("Time", "s", "s", role="time", category="time")
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
              "N", "N", role="truth", category="tire")
    _register("Kappa_" + corner, "1", "1", role="truth", category="tire")
    _register("Alpha_" + corner, "deg", "rad", pi / 180, "truth", "tire")
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


def no_truth_channels(columns):
    for name in columns:
        if channel(name).role == "truth":
            raise GroundTruthLeakageError("Estimator cannot access %s" % name)
    return True


@dataclass
class RunData:
    observable: pd.DataFrame
    truth: pd.DataFrame
    metadata: dict

    def estimator_view(self, columns=None):
        names = list(self.observable.columns) if columns is None else list(columns)
        no_truth_channels(names)
        return self.observable.loc[:, names].copy()

    def evaluator_view(self, columns=None):
        frame = self.observable.join(self.truth.drop(columns="Time", errors="ignore"))
        return frame.copy() if columns is None else frame.loc[:, columns].copy()


def load_run(path, estimator_channels=None):
    """Workflow helper: load native CSV once into SI role partitions.

    This is the research-workflow entry point (estimator/evaluator isolation),
    NOT the default reader - carsim_batch.read_run_csv() returns every
    registered channel without role checks. An explicit estimator whitelist
    also makes unselected sensor-eligible channels inaccessible through
    estimator_view(). It is recorded in metadata.
    """
    df = pd.read_csv(path).drop(columns=list(UNRELIABLE_COLS), errors="ignore")
    if "Time" not in df:
        raise ValueError("Missing Time channel")
    specs = {name: channel(name) for name in df}
    for name, spec in specs.items():
        df[name] = pd.to_numeric(df[name], errors="raise") * spec.scale
    observable = [n for n, s in specs.items() if s.role != "truth"]
    if estimator_channels is not None:
        no_truth_channels(estimator_channels)
        observable = list(dict.fromkeys(["Time"] + list(estimator_channels)))
        missing = set(observable) - set(df.columns)
        if missing:
            raise ValueError("Missing estimator channels: %s" % sorted(missing))
    truth = [n for n in df if n not in observable and n != "Time"]
    return RunData(df[observable].copy(), df[["Time"] + truth].copy(), {
        "units": {n: asdict(s) for n, s in specs.items()},
        "estimator_channels": observable, "source": str(path),
    })
