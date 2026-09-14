"""Core run validation: fresh artifacts, complete time grid, parameter echo.

check_run() reports structured issues (error / warning / info) instead of
raising; validate_run() is the compatibility wrapper that raises ValueError
on the first error and returns the legacy metrics dict. Failure semantics of
the previously field-validated checks are unchanged.
"""
from dataclasses import asdict, dataclass, field
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass
class ValidationIssue:
    severity: str   # "error" | "warning" | "info"
    code: str
    message: str


@dataclass
class RunValidationResult:
    passed: bool
    issues: list = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def errors(self):
        return [i for i in self.issues if i.severity == "error"]

    def warnings(self):
        return [i for i in self.issues if i.severity == "warning"]


def check_run(directory, simulation, required_channels, started_at=None,
              expected_parameters=None, minimum_speed_mps=None,
              solver_stdout=None):
    """Validate a finished run directory; never raises. Missing run.csv /
    run_echo short-circuit with a single error (nothing else can be checked)."""
    directory = Path(directory)
    issues = []

    def add(severity, code, message):
        issues.append(ValidationIssue(severity, code, message))

    paths = {"run_csv": directory / "run.csv", "run_echo": directory / "run_echo.par"}
    fatal = False
    for key, path in paths.items():
        if not path.is_file() or path.stat().st_size == 0:
            add("error", "missing_artifact", "Missing or empty result: %s" % path)
            fatal = True
        elif started_at is not None and path.stat().st_mtime < started_at:
            add("error", "stale_artifact", "Stale result: %s" % path)
            fatal = True
    if not fatal:
        metrics, fatal = _check_contents(directory, simulation, required_channels,
                                         expected_parameters, minimum_speed_mps, add)
    else:
        metrics = {}
    if solver_stdout is not None and "Termination at simulation time" not in solver_stdout:
        add("error", "solver_no_termination",
            "Solver output lacks 'Termination at simulation time'")
    if not (directory / "run_log.txt").is_file():
        add("warning", "missing_run_log", "run_log.txt absent; dataset provenance not recorded")
    return RunValidationResult(passed=not any(i.severity == "error" for i in issues),
                               issues=issues, metrics=metrics)


def _check_contents(directory, simulation, required_channels, expected_parameters,
                    minimum_speed_mps, add):
    df = pd.read_csv(directory / "run.csv")
    missing = set(["Time"] + list(required_channels)) - set(df.columns)
    if missing:
        add("error", "missing_channels", "Missing required channels: %s" % sorted(missing))
        return {}, True
    try:
        values = df.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        add("error", "non_numeric", "Non-numeric result: %s" % exc)
        return {}, True
    if not np.isfinite(values).all():
        add("error", "nonfinite_values", "Result contains NaN/inf")
        return {}, True
    t = df.Time.to_numpy(dtype=float)
    expected_count = round(simulation.duration / simulation.dt) + 1
    tolerance = max(1e-8, simulation.dt * 1e-4)
    if len(t) != expected_count:
        add("error", "sample_count", "Unexpected sample count: %s, expected %s"
            % (len(t), expected_count))
        return {}, True
    if not (np.diff(t) > 0).all() or not np.allclose(t, np.arange(expected_count) * simulation.dt,
                                                     atol=tolerance, rtol=0):
        add("error", "time_grid", "Time must be strictly increasing and match requested grid/TSTOP")
        return {}, True
    metrics = {"samples": len(t), "final_time_s": float(t[-1]),
               "minimum_speed_mps": minimum_speed_mps}
    echo = (directory / "run_echo.par").read_text(encoding="utf-8", errors="replace")
    actual = {}
    echo_ok = True
    for key, requested in (expected_parameters or {}).items():
        matches = re.findall(r"^\s*" + re.escape(key) + r"\s+([-+0-9.eEdD]+)(?=\s|$)", echo, re.M)
        if not matches:
            add("error", "echo_absent", "Parameter absent from echo: %s" % key)
            echo_ok = False
            continue
        value = float(matches[-1].replace("D", "E").replace("d", "e"))
        if not math.isclose(value, requested, rel_tol=1e-6, abs_tol=1e-8):
            add("error", "echo_mismatch", "Echo mismatch %s: requested %s, actual %s"
                % (key, requested, value))
            echo_ok = False
            continue
        actual[key] = value
    metrics["echo_parameters"] = actual
    if minimum_speed_mps is not None:
        if "Vx" not in df or df.Vx.abs().max() / 3.6 < minimum_speed_mps:
            add("error", "movement_threshold",
                "Vehicle did not meet requested movement threshold")
            echo_ok = False
    return metrics, not echo_ok


def validate_run(directory, simulation, required_channels, started_at=None,
                 expected_parameters=None, minimum_speed_mps=None,
                 solver_stdout=None):
    """Compatibility wrapper: raise ValueError on the first error, return the
    legacy metrics dict (with passed=True) otherwise."""
    result = check_run(directory, simulation, required_channels, started_at,
                       expected_parameters, minimum_speed_mps, solver_stdout)
    if not result.passed:
        first = result.errors()[0]
        raise ValueError("%s: %s" % (first.code, first.message))
    return dict(result.metrics, passed=True, issues=[asdict(i) for i in result.issues])
