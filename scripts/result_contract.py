"""Explicit native CSV units and estimator/evaluator access boundaries.

Observable means sensor-eligible, not a claim that the vehicle has that sensor.
Experiments must declare the actual estimator whitelist (e.g. omit Vy for a
lateral-velocity estimator). Unknown channels fail closed.
"""
from dataclasses import asdict, dataclass
from math import pi

import pandas as pd


class GroundTruthLeakageError(ValueError):
    pass


@dataclass(frozen=True)
class Channel:
    source_unit: str
    si_unit: str
    scale: float
    role: str
    source: str = "CarSim native run.csv"


CHANNEL_REGISTRY = {}


def _register(names, native, si, scale=1.0, role="observable"):
    for name in names.split():
        CHANNEL_REGISTRY[name] = Channel(native, si, scale, role)


_register("Time", "s", "s", role="time")
_register("Vx Vy", "km/h", "m/s", 1 / 3.6)
_register("Ax Ay", "g", "m/s^2", 9.80665)
_register("AVz", "deg/s", "rad/s", pi / 180)
_register("Roll Pitch Yaw", "deg", "rad", pi / 180)
_register("Xo Yo Zo Station", "m", "m")
for corner in ("L1", "R1", "L2", "R2"):
    _register("Vx_" + corner, "km/h", "m/s", 1 / 3.6)
    _register("Steer_" + corner, "deg", "rad", pi / 180)
    _register("AVy_" + corner, "rpm", "rad/s", 2 * pi / 60)
    _register("My_Dr_" + corner + " My_Bk_" + corner, "N*m", "N*m")
    _register(" ".join(p + corner for p in ("Fx_", "Fy_", "Fz_")),
              "N", "N", role="truth")
    _register("Kappa_" + corner, "1", "1", role="truth")
    _register("Alpha_" + corner, "deg", "rad", pi / 180, "truth")
_register("AV_Mt_D1_L AV_Mt_D1_R AV_Mt_D2_L AV_Mt_D2_R",
          "rpm", "rad/s", 2 * pi / 60)

# WRT keyword spellings differ from CSV header spellings for these two angles.
OUTPUT_ALIASES = {"ROLL": "Roll", "PITCH": "Pitch"}
UNRELIABLE_COLS = ("Lat_Veh", "Lat_Targ")


def channel(name):
    canonical = OUTPUT_ALIASES.get(name, name)
    try:
        return CHANNEL_REGISTRY[canonical]
    except KeyError:
        raise ValueError("Unregistered channel %r; verify units and role first" % name) from None


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
    """Load native CSV once into SI partitions; reject unknown units/columns.

    An explicit estimator whitelist also makes unselected sensor-eligible
    channels inaccessible through estimator_view(). It is recorded in metadata.
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
