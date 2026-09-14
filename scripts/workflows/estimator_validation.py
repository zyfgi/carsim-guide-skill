"""Research-workflow layer: estimator/evaluator isolation policy.

The CarSim core (carsim_batch.py, result_contract.py) reads every registered
channel without any restriction. This module owns the OPTIONAL policy used by
estimator/machine-learning workflows that treat tire outputs and similar
simulator-internal channels as privileged information:

  - PRIVILEGED_PREFIXES / is_privileged          - the workflow-owned marking
  - GroundTruthLeakageError / no_privileged_channels - the enforcing policy
  - RunData (+ estimator_view / evaluator_view)  - partitioned SI data
  - load_run                                     - one-shot native CSV loader

The privileged set is a workflow default policy, not a property of the
channels themselves; it is deliberately NOT written back into the core
registry. Import direction: workflows -> core, never the reverse.
"""
from dataclasses import asdict, dataclass

import pandas as pd

from result_contract import UNRELIABLE_COLS, channel

# Workflow default policy: simulator-internal tire outputs are privileged for
# estimator inputs. Workflow authors may maintain their own set; the core
# registry knows nothing about it.
PRIVILEGED_PREFIXES = ("Fx_", "Fy_", "Fz_", "Kappa_", "Alpha_")


def is_privileged(name):
    """Whether the workflow's default policy marks this channel privileged."""
    return name.startswith(PRIVILEGED_PREFIXES)


class GroundTruthLeakageError(ValueError):
    """Raised when a channel the workflow marked privileged reaches
    estimator code."""


def no_privileged_channels(columns):
    """Privileged policy: reject privileged channels as estimator inputs."""
    for name in columns:
        if is_privileged(name):
            raise GroundTruthLeakageError("Estimator cannot access %s" % name)
    return True


# Deprecated alias (the pre-P1 name of the policy check).
no_truth_channels = no_privileged_channels


@dataclass
class RunData:
    observable: pd.DataFrame
    truth: pd.DataFrame
    metadata: dict

    def estimator_view(self, columns=None):
        names = list(self.observable.columns) if columns is None else list(columns)
        no_privileged_channels(names)
        return self.observable.loc[:, names].copy()

    def evaluator_view(self, columns=None):
        frame = self.observable.join(self.truth.drop(columns="Time", errors="ignore"))
        return frame.copy() if columns is None else frame.loc[:, columns].copy()


def load_run(path, estimator_channels=None):
    """Load native CSV once into SI partitions; reject unknown units/columns.

    This is the research-workflow entry point (estimator/evaluator isolation),
    NOT the default reader - carsim_batch.read_run_csv() returns every
    registered channel without role checks. An explicit estimator whitelist
    also makes unselected non-privileged channels inaccessible through
    estimator_view(). It is recorded in metadata.
    """
    df = pd.read_csv(path).drop(columns=list(UNRELIABLE_COLS), errors="ignore")
    if "Time" not in df:
        raise ValueError("Missing Time channel")
    specs = {name: channel(name) for name in df}
    for name, spec in specs.items():
        df[name] = pd.to_numeric(df[name], errors="raise") * spec.scale
    observable = [n for n in df if not is_privileged(n)]
    if estimator_channels is not None:
        no_privileged_channels(estimator_channels)
        observable = list(dict.fromkeys(["Time"] + list(estimator_channels)))
        missing = set(observable) - set(df.columns)
        if missing:
            raise ValueError("Missing estimator channels: %s" % sorted(missing))
    truth = [n for n in df if n not in observable and n != "Time"]
    return RunData(df[observable].copy(), df[["Time"] + truth].copy(), {
        "units": {n: asdict(s) for n, s in specs.items()},
        "estimator_channels": observable, "source": str(path),
    })
