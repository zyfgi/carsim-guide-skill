"""P1 generic scenario runner, run manifest and structured validation.

Fake runtime + fake solver; no real CarSim required.
"""
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import carsim_batch as cb  # noqa: E402
from base_registry import bind_base, sha256  # noqa: E402
from scenario_runner import (MANIFEST_NAME, compile_scenario,  # noqa: E402
                             run_scenario, verify_compiled)
from validate_run import check_run  # noqa: E402
from scenario_schema import SimulationConfig  # noqa: E402


@pytest.fixture()
def runtime(tmp_path, monkeypatch):
    prog = tmp_path / "CarSim2024.0_Prog"
    data = tmp_path / "CarSim2024.0_Data"
    (prog / "Programs" / "solvers").mkdir(parents=True)
    data.mkdir()
    (prog / "Programs" / "solvers" / "carsim_64.dll").write_text("fake dll")
    (prog / "Programs" / "VS_SolverWrapper_CLI_64.exe").write_text("fake cli")
    base = tmp_path / "Run_all.par"
    base.write_text("PARSFILE\nEND\n")
    registry = tmp_path / "bases.local.json"
    bind_base(registry, "sedan", base, "2024.0", run_control="rc", vehicle="C-Class")
    monkeypatch.setenv("CARSIM_GUIDE_CONFIG", str(tmp_path / "absent.json"))
    for key in ("CARSIM_PROG", "CARSIM_DATADIR", "CARSIM_BASE"):
        monkeypatch.delenv(key, raising=False)
    return prog, data, base, registry


@pytest.fixture()
def scenario():
    return {
        "schema_version": 1,
        "scenario": {"id": "cruise_50"},
        "base": {"name": "sedan"},
        "simulation": {"dt": 0.005, "duration": 0.1},
        "road": {"mu": 0.85},
        "maneuver": {"speed_kmh": [[0, 36], [0.1, 36]],
                     "steering_deg": [[0, 0], [0.1, 0]]},
        "vehicle": {"sprung_mass_kg": 1500},
        "outputs": {"channels": ["Vx", "AVz", "Fx_L1"]},
        "validation": {"minimum_speed_mps": 1.0},
    }


def fake_solver_outputs(directory, scenario):
    """Write a synthetic, exactly-gridded run.csv + matching echo."""
    dt = scenario["simulation"]["dt"]
    duration = scenario["simulation"]["duration"]
    t = np.arange(round(duration / dt) + 1) * dt
    pd.DataFrame({"Time": t, "Vx": 36.0, "AVz": 1.0, "Fx_L1": 500.0}).to_csv(
        Path(directory) / "run.csv", index=False)
    echo = ["M_SU 1500", "TSTEP %s" % dt, "TSTOP %s" % duration, "IPRINT 1"]
    (Path(directory) / "run_echo.par").write_text("\n".join(echo), encoding="utf-8")
    (Path(directory) / "run_log.txt").write_text("fake log", encoding="utf-8")
    for name in ("run.csv", "run_echo.par", "run_log.txt"):
        os.utime(Path(directory) / name, (time.time() + .01,) * 2)


def test_manifest_created_and_passed(runtime, scenario, monkeypatch, tmp_path):
    prog, data, base, registry = runtime

    def fake_solver(sim, *args, **kw):
        fake_solver_outputs(Path(sim).parent, scenario)
        return "Termination at simulation time = 0.1"

    monkeypatch.setattr(cb, "run_solver", fake_solver)
    out = tmp_path / "runs"
    directory = run_scenario(scenario, registry, out, str(prog), str(data), execute=True)
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["run"]["status"] == "passed"
    assert manifest["base"]["name"] == "sedan"
    assert manifest["carsim"]["dll_sha256"] == sha256(prog / "Programs" / "solvers" / "carsim_64.dll")
    assert manifest["validation"]["passed"] is True
    assert manifest["validation"]["metrics"]["echo_parameters"]["M_SU"] == 1500.0
    assert manifest["artifacts"]["run_csv"].endswith("run.csv")
    # core manifest: no research fields anywhere
    text = (directory / MANIFEST_NAME).read_text(encoding="utf-8")
    for word in ("estimator", "evaluator", "sensor", "torch", "truth"):
        assert word not in text, word


def test_compile_only_dry_run(runtime, scenario):
    prog, data, base, registry = runtime
    directory = run_scenario(scenario, registry, runtime[0].parent / "dry", str(prog), str(data))
    manifest = json.loads((directory / MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["run"]["status"] == "compiled"
    assert (directory / "override.par").is_file() and (directory / "simfile.sim").is_file()
    assert not (directory / "run.csv").exists()
    text = (directory / "override.par").read_text(encoding="utf-8")
    assert "M_SU 1500" in text and "WRT_Fx_L1" in text  # tire output allowed
    with pytest.raises(FileExistsError):
        run_scenario(scenario, registry, runtime[0].parent / "dry", str(prog), str(data))


def test_verify_compiled_detects_tampering(runtime, scenario):
    prog, data, base, registry = runtime
    directory = (runtime[0].parent / "tamper")
    from base_registry import resolve_base
    entry = resolve_base(registry, "sedan", str(prog))
    info = compile_scenario(scenario, entry, str(prog), str(data), directory)
    assert verify_compiled(directory, info, entry) == []
    par = directory / "override.par"
    par.write_text(par.read_text(encoding="utf-8").replace("TSTEP 0.005", "TSTEP 0.01"),
                   encoding="utf-8")
    issues = verify_compiled(directory, info, entry)
    assert any(i.code == "dt_mismatch" for i in issues)
    (directory / "base_Run_all.par").write_text("changed base")
    issues = verify_compiled(directory, info, entry)
    assert any(i.code == "base_changed" for i in issues)


def test_failed_run_keeps_manifest(runtime, scenario, monkeypatch):
    prog, data, base, registry = runtime
    monkeypatch.setattr(cb, "run_solver", lambda *a, **k: "no termination line")
    with pytest.raises(ValueError):
        run_scenario(scenario, registry, runtime[0].parent / "bad", str(prog), str(data),
                     execute=True)
    manifest = json.loads((runtime[0].parent / "bad" / "cruise_50" / MANIFEST_NAME)
                          .read_text(encoding="utf-8"))
    assert manifest["run"]["status"] == "failed" and manifest["error"]
    assert not (runtime[0].parent / "bad" / "cruise_50" / "run.csv").exists()


def test_check_run_severities(runtime, scenario):
    prog, data, base, registry = runtime
    d = runtime[0].parent / "valcheck"
    d.mkdir()
    fake_solver_outputs(d, scenario)
    result = check_run(d, SimulationConfig(0.005, 0.1), ["Vx"], None, {"M_SU": 1500.0})
    assert result.passed and result.errors() == [] and result.metrics["samples"] == 21
    df = pd.read_csv(d / "run.csv")
    df.loc[2, "Vx"] = float("nan")
    df.to_csv(d / "run.csv", index=False)
    result = check_run(d, SimulationConfig(0.005, 0.1), ["Vx"])
    assert not result.passed
    assert result.errors()[0].code == "nonfinite_values"
    # a missing run_log is a warning, not an error
    d2 = runtime[0].parent / "valcheck2"
    d2.mkdir()
    fake_solver_outputs(d2, scenario)
    (d2 / "run_log.txt").unlink()
    result = check_run(d2, SimulationConfig(0.005, 0.1), ["Vx"])
    assert result.passed and result.warnings()[0].code == "missing_run_log"
