"""Behavioral regression suite using synthetic native CSVs and a fake solver.

No assertions here claim validation of CarSim physics or a licensed run.
"""
import copy
import json
import math
import os
from pathlib import Path
import re
import sys
import time

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import carsim_batch as cb  # noqa: E402
import experiment_runner as er  # noqa: E402
from result_contract import GroundTruthLeakageError, load_run  # noqa: E402
from scenario_schema import SimulationConfig, VehicleOverrides, load_experiment, validate_experiment  # noqa: E402
from sensor_replay import replay, estimator_stream  # noqa: E402
from validate_run import validate_run  # noqa: E402
from vehicle_registry import bind_vehicle, resolve_vehicle, product_version  # noqa: E402


@pytest.fixture()
def config():
    return {"schema_version": 1, "experiment": {"id": "test_run", "seed": 42},
            "vehicle": {"base": "ev"}, "simulation": {"dt": .005, "duration": .1},
            "road": {"mu": .8}, "vehicle_parameters": {"sprung_mass_kg": 1500, "cg_y_m": .15},
            "maneuver": {"speed_kmh": [[0, 36], [.1, 36]], "steering_deg": [[0, 0], [.1, 0]]},
            "outputs": {"estimator": ["Vx", "AV_Mt_D1_L"], "evaluator": ["Fx_L1"]},
            "sensors": {"speed": {"channels": ["Vx"], "sample_hz": 100},
                        "motor": {"channels": ["AV_Mt_D1_L"], "sample_hz": 100}},
            "validation": {"minimum_speed_mps": 1}}


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
    registry = tmp_path / "vehicles.json"
    bind_vehicle(registry, "ev", base, "2024.0", "run-uuid", "four-motor EV")
    monkeypatch.setenv("CARSIM_GUIDE_CONFIG", str(tmp_path / "absent-cache.json"))
    for key in ("CARSIM_PROG", "CARSIM_DATADIR", "CARSIM_BASE"):
        monkeypatch.delenv(key, raising=False)
    return prog, data, base, registry


def native_run(directory, config):
    dt = config["simulation"]["dt"]
    duration = config["simulation"]["duration"]
    t = np.arange(round(duration / dt) + 1) * dt
    pd.DataFrame({"Time": t, "Vx": 36., "AV_Mt_D1_L": 60., "Fx_L1": 500.}).to_csv(directory / "run.csv", index=False)
    echo = VehicleOverrides(**config["vehicle_parameters"]).lines()
    echo += ["TSTEP %s" % dt, "TSTOP %s" % duration, "IPRINT 1"]
    (directory / "run_echo.par").write_text("\n".join(echo))


def test_step_single_source_and_vehicle_units(runtime, tmp_path):
    prog, data, base, _ = runtime
    simulation = SimulationConfig(.005, .1)
    sim = cb.make_scenario(tmp_path / "scenario", str(base), str(prog), str(data),
                           config=simulation, vehicle_overrides=VehicleOverrides(cg_y_m=.15))
    text = (Path(sim).parent / "override.par").read_text()
    dt_par = float(re.search(r"^TSTEP (.+)$", text, re.M)[1])
    dt_sim = float(re.search(r"^EXT_MODEL_STEP (.+)$", Path(sim).read_text(), re.M)[1])
    assert dt_par == dt_sim == .005
    assert "Y_CG_SU 150" in text
    assert "WRT_Fx_L1" not in text
    with pytest.raises(ValueError, match="not both"):
        cb.make_scenario(tmp_path / "bad", str(base), str(prog), str(data), config=simulation, tstep=.01)
    with pytest.raises(ValueError, match="conflicts"):
        cb.override_par(str(base), .1, [(0, 1), (.1, 1)], [(0, 0), (.1, 0)], unsafe_extra_lines=["TSTEP .02"])


@pytest.mark.parametrize("dt,duration", [(0, 1), (-1, 1), (.03, .1), (.001, float("inf")), (float("nan"), 1)])
def test_invalid_timing(dt, duration):
    with pytest.raises(ValueError):
        SimulationConfig(dt, duration)


def test_estimator_truth_isolation_optional_workflow(tmp_path, config):
    """Estimator/evaluator isolation lives in the OPTIONAL research workflow
    (load_run + estimator_view); the core reader never applies it."""
    native_run(tmp_path, config)
    run = load_run(tmp_path / "run.csv", ["Vx"])
    assert run.observable.Vx.iloc[0] == 10
    assert run.evaluator_view().AV_Mt_D1_L.iloc[0] == pytest.approx(2 * math.pi)
    assert "Fx_L1" not in run.estimator_view()
    with pytest.raises(GroundTruthLeakageError):
        run.estimator_view(["Vx", "Fx_L1"])
    with pytest.raises(KeyError):
        run.estimator_view(["AV_Mt_D1_L"])  # sensor-eligible but not whitelisted
    # core reader: tire outputs pass through untouched, no isolation rules
    core = cb.read_run_csv(tmp_path / "run.csv")
    assert core.Fx_L1.iloc[0] == 500
    view = run.estimator_view()
    view.loc[0, "Vx"] = -100
    assert run.observable.Vx.iloc[0] == 10


@pytest.mark.parametrize("mutation", [
    lambda c: c["outputs"]["estimator"].append("Fx_L1"),
    lambda c: c["vehicle_parameters"].update(mass_kg=100),
    lambda c: c["maneuver"].update(speed_kmh=[[0, 10], [0, 20]]),
    lambda c: c["sensors"]["speed"].update(sample_hz=1000),
    lambda c: c["sensors"]["speed"].update(channels=["AVz"]),
    lambda c: c["experiment"].update(id="../escape"),
    lambda c: c["road"].update(mu=float("nan")),
    lambda c: c["outputs"]["estimator"].append("ROLL"),
])
def test_schema_rejects_invalid_intent(config, mutation):
    mutation(config)
    with pytest.raises(Exception):
        validate_experiment(config)


def test_base_binding_hash_and_version(runtime):
    prog, _, base, registry = runtime
    assert resolve_vehicle(registry, "ev", str(prog))["run_control"] == "run-uuid"
    assert product_version("C:/CarSim2025.1_Prog") == "2025.1"
    with pytest.raises(ValueError, match="disagrees"):
        resolve_vehicle(registry, "ev", "C:/CarSim2025.1_Prog")
    with pytest.raises(ValueError, match="Cannot infer"):
        product_version("C:/custom_install")
    base.write_text("changed vehicle")
    with pytest.raises(ValueError, match="SHA256"):
        resolve_vehicle(registry, "ev", str(prog))


def test_causal_seeded_replay():
    t = np.arange(101) * .01
    source = pd.DataFrame({"Time": t, "Vx": t})
    spec = {"speed": {"channels": ["Vx"], "sample_hz": 33, "latency_s": .02, "jitter_s": .03}}
    packets = replay(source, spec, 7)["speed"]
    assert (packets.arrival_time_s >= packets.sample_time_s).all()
    assert (packets.Vx <= packets.sample_time_s).all()
    assert packets.arrival_time_s.is_monotonic_increasing
    spec["speed"].update(noise_std=.1, drop_probability=.3, bias=.2, quantization=.05)
    a, b = replay(source, spec, 7), replay(source, spec, 7)
    pd.testing.assert_frame_equal(a["speed"], b["speed"])
    assert not a["speed"].equals(replay(source, spec, 8)["speed"])
    assert len(list(estimator_stream(a))) == len(a["speed"])
    spec["speed"]["drop_probability"] = 1
    assert replay(source, spec, 7)["speed"].empty
    with pytest.raises(GroundTruthLeakageError):
        replay(source.assign(Fx_L1=1), spec, 1)


@pytest.mark.parametrize("failure", ["stale", "short", "duplicate", "nan", "missing", "echo", "stationary"])
def test_postrun_rejects_invalid_experiment(tmp_path, config, failure):
    native_run(tmp_path, config)
    start = time.time() - 1
    path = tmp_path / "run.csv"
    df = pd.read_csv(path)
    if failure == "stale":
        os.utime(path, (1, 1))
    elif failure == "echo":
        (tmp_path / "run_echo.par").write_text("M_SU 1200\nY_CG_SU 150\n")
    else:
        if failure == "short":
            df = df.iloc[:-1]
        elif failure == "duplicate":
            df.loc[2, "Time"] = df.loc[1, "Time"]
        elif failure == "nan":
            df.loc[2, "Vx"] = float("nan")
        elif failure == "missing":
            df = df.drop(columns="Vx")
        elif failure == "stationary":
            df["Vx"] = 0
        df.to_csv(path, index=False)
    with pytest.raises(ValueError):
        validate_run(tmp_path, SimulationConfig(**config["simulation"]), ["Vx"], start,
                     VehicleOverrides(**config["vehicle_parameters"]).keywords(), 1)


def test_runner_end_to_end_and_failure_manifest(tmp_path, runtime, config, monkeypatch):
    prog, data, _, registry = runtime

    def fake_solver(sim, *args):
        native_run(Path(sim).parent, config)
        # Deterministic filesystem timestamps for the freshness check.
        for name in ("run.csv", "run_echo.par"):
            os.utime(Path(sim).parent / name, (time.time() + .01,) * 2)
        return "Termination at simulation time = 0.1"

    monkeypatch.setattr(er, "run_solver", fake_solver)
    directory = er.run_experiment(config, registry, tmp_path / "output", str(prog), str(data), execute=True)
    manifest = json.loads((directory / "manifest.json").read_text())
    assert manifest["status"] == "passed"
    assert manifest["validation"]["echo_parameters"]["M_SU"] == 1500
    assert manifest["vehicle"]["base_sha256"] == cb.sha256(directory / "base_Run_all.par")
    assert "Fx_L1" not in pd.read_csv(directory / "observable.csv")
    assert "Fx_L1" in pd.read_csv(directory / "truth.csv")
    assert manifest["sensor_packets"]["speed"] == 11
    assert "sensor_speed.csv" in manifest["output_sha256"]
    with pytest.raises(FileExistsError):
        er.run_experiment(config, registry, tmp_path / "output", str(prog), str(data))
    failed = copy.deepcopy(config)
    failed["experiment"]["id"] = "failed"
    monkeypatch.setattr(er, "run_solver", lambda *a: "Termination at simulation time = 0.1")
    with pytest.raises(ValueError, match="Missing"):
        er.run_experiment(failed, registry, tmp_path / "output", str(prog), str(data), execute=True)
    manifest = json.loads((tmp_path / "output/failed/manifest.json").read_text())
    assert manifest["status"] == "failed" and "Missing" in manifest["error"]
    assert not (tmp_path / "output/failed/observable.csv").exists()


def test_compile_only_and_sweep(runtime, tmp_path, config, monkeypatch):
    prog, data, _, registry = runtime
    monkeypatch.setattr(er, "run_solver", lambda *a: pytest.fail("dry-run called solver"))
    config["sweep"] = [{"id": "low", "road": {"mu": .4}}, {"id": "high", "road": {"mu": .9}}]
    variants = er.expand_experiments(config)
    for item in variants:
        directory = er.run_experiment(item, registry, tmp_path / "output", str(prog), str(data))
        assert json.loads((directory / "manifest.json").read_text())["status"] == "compiled"
    assert variants[0]["road"]["mu"] == .4 and config["road"]["mu"] == .8
    config["sweep"].append(config["sweep"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        er.expand_experiments(config)


@pytest.mark.parametrize("name", ["basic_run", "parameter_sweep", "tire_force_estimation", "vehicle_parameter_id"])
def test_shipped_yaml_examples_are_valid(name):
    config = load_experiment(Path(__file__).resolve().parents[1] / "examples" / (name + ".yaml"))
    for variant in er.expand_experiments(config):
        validate_experiment(variant)


def test_legacy_tstep_and_aliases(runtime, tmp_path):
    prog, data, base, _ = runtime
    sim = cb.make_scenario(tmp_path / "legacy", str(base), str(prog), str(data),
                           tstep=.005, tstop=.1, outputs=["Roll", "Pitch"])
    text = (Path(sim).parent / "override.par").read_text()
    assert float(re.search(r"^TSTEP (.+)$", text, re.M)[1]) == .005
    assert float(re.search(r"^EXT_MODEL_STEP (.+)$", Path(sim).read_text(), re.M)[1]) == .005
    assert "WRT_ROLL" in text and "WRT_PITCH" in text


def test_schema_typo_in_sweep_is_not_silently_ignored(config):
    config["sweep"] = [{"id": "variant", "vehicle_parameters": {"cg_y_mm": 150}}]
    with pytest.raises(Exception):
        validate_experiment(config)
