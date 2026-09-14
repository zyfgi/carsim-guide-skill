"""Post-run acceptance: fresh artifacts, complete time grid and parameter echo."""
import math
import re
from pathlib import Path

import numpy as np
import pandas as pd


def validate_run(directory, simulation, required_channels, started_at=None,
                 expected_parameters=None, minimum_speed_mps=None):
    directory = Path(directory)
    paths = [directory / "run.csv", directory / "run_echo.par"]
    for path in paths:
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError("Missing or empty result: %s" % path)
        if started_at is not None and path.stat().st_mtime < started_at:
            raise ValueError("Stale result: %s" % path)
    df = pd.read_csv(paths[0])
    missing = set(["Time"] + list(required_channels)) - set(df.columns)
    if missing:
        raise ValueError("Missing required channels: %s" % sorted(missing))
    try:
        values = df.to_numpy(dtype=float)
    except (TypeError, ValueError) as exc:
        raise ValueError("Non-numeric result") from exc
    if not np.isfinite(values).all():
        raise ValueError("Result contains NaN/inf")
    t = df.Time.to_numpy(dtype=float)
    expected_count = round(simulation.duration / simulation.dt) + 1
    tolerance = max(1e-8, simulation.dt * 1e-4)
    if len(t) != expected_count:
        raise ValueError("Unexpected sample count: %s, expected %s" % (len(t), expected_count))
    if not (np.diff(t) > 0).all() or not np.allclose(t, np.arange(expected_count) * simulation.dt,
                                                   atol=tolerance, rtol=0):
        raise ValueError("Time must be strictly increasing and match requested grid/TSTOP")
    actual = {}
    echo = paths[1].read_text(encoding="utf-8", errors="replace")
    for key, requested in (expected_parameters or {}).items():
        matches = re.findall(r"^\s*" + re.escape(key) + r"\s+([-+0-9.eEdD]+)(?=\s|$)", echo, re.M)
        if not matches:
            raise ValueError("Parameter absent from echo: %s" % key)
        value = float(matches[-1].replace("D", "E").replace("d", "e"))
        if not math.isclose(value, requested, rel_tol=1e-6, abs_tol=1e-8):
            raise ValueError("Echo mismatch %s: requested %s, actual %s" % (key, requested, value))
        actual[key] = value
    if minimum_speed_mps is not None:
        if "Vx" not in df or df.Vx.abs().max() / 3.6 < minimum_speed_mps:
            raise ValueError("Vehicle did not meet requested movement threshold")
    return {"passed": True, "samples": len(t), "final_time_s": float(t[-1]),
            "echo_parameters": actual, "minimum_speed_mps": minimum_speed_mps}
