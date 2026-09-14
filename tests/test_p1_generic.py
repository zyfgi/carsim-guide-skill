"""P1 generic-layer tests: scenario schema + base registry. No CarSim needed."""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import base_registry as br  # noqa: E402
from scenario_schema import validate_scenario  # noqa: E402


@pytest.fixture()
def scenario():
    return {
        "schema_version": 1,
        "scenario": {"id": "double_lane_change_mu08"},
        "base": {"name": "distributed_ev"},
        "simulation": {"dt": 0.001, "duration": 30.0},
        "road": {"friction": 0.8},
        "maneuver": {"speed_kmh": [[0, 50], [30, 50]],
                     "steering_deg": [[0, 0], [5, 20], [6, -20], [30, 0]]},
        "vehicle": {"sprung_mass_kg": 1250.0},
        "parameters": [{"keyword": "M_SU", "value": 1250.0}],
        "outputs": {"channels": ["Vx", "Vy", "AVz", "Fx_L1", "Fy_L1"]},
        "validation": {"minimum_speed_mps": 1.0},
    }


def test_generic_scenario_validates(scenario):
    assert validate_scenario(scenario) is scenario


def test_generic_scenario_has_no_estimator_fields(scenario):
    for key in ("estimator", "evaluator", "sensors", "experiment", "seed", "sweep"):
        scenario["outputs"] = {"channels": ["Vx"], key: ["Vx"]} if key.startswith(("est", "eval")) \
            else scenario.update({key: 1})
        with pytest.raises(Exception):
            validate_scenario(scenario)


def test_scenario_output_allows_tire_channels(scenario):
    scenario["outputs"]["channels"] = ["Fx_L1", "Fy_L1", "Fz_L1", "Kappa_L1"]
    validate_scenario(scenario)  # tire outputs are ordinary channels


def test_scenario_time_validation(scenario):
    for bad in ([[1, 50], [30, 50]], [[0, 50], [0, 20]], [[0, 50], [40, 50]]):
        scenario["maneuver"]["speed_kmh"] = bad
        with pytest.raises(ValueError, match="times must start"):
            validate_scenario(scenario)


def test_scenario_unknown_channel_fails(scenario):
    scenario["outputs"]["channels"] = ["Vx", "Madeup_Channel"]
    with pytest.raises(ValueError, match="Unregistered"):
        validate_scenario(scenario)


def test_scenario_parameter_checks(scenario):
    scenario["parameters"] = [{"keyword": "m_su", "value": 1.0}]
    with pytest.raises(Exception):  # schema: keyword must be upper-case tokens
        validate_scenario(scenario)
    scenario["parameters"] = [{"keyword": "M_SU", "value": float("nan")}]
    with pytest.raises(ValueError, match="finite"):
        validate_scenario(scenario)


# ---------------------------------------------------------------- base registry
@pytest.fixture()
def bound(tmp_path):
    base = tmp_path / "Run_all.par"
    base.write_text("PARSFILE\nEND\n")
    registry = tmp_path / "bases.local.json"
    br.bind_base(registry, "sedan", base, "2024.0",
                 run_control="rc-1", vehicle="C-Class", notes="quick start")
    return registry, base


def test_base_registry_explicit_binding(bound):
    registry, base = bound
    entry = br.resolve_base(registry, "sedan", "C:/CarSim2024.0_Prog")
    assert entry["base_run_all"] == str(base.resolve())
    assert entry["base_sha256"] == br.sha256(base)
    assert entry["run_control"] == "rc-1"
    with pytest.raises(ValueError, match="Unknown base name"):
        br.resolve_base(registry, "suv", "C:/CarSim2024.0_Prog")
    with pytest.raises(ValueError, match="already bound"):
        br.bind_base(registry, "sedan", base, "2024.0")


def test_base_hash_mismatch(bound):
    registry, base = bound
    base.write_text("PARSFILE\nCHANGED\n")
    with pytest.raises(ValueError, match="SHA256"):
        br.resolve_base(registry, "sedan", "C:/CarSim2024.0_Prog")


def test_base_version_guard(bound):
    registry, _ = bound
    with pytest.raises(ValueError, match="disagrees"):
        br.resolve_base(registry, "sedan", "C:/CarSim2025.1_Prog")


def test_vehicle_registry_compatibility(tmp_path, bound):
    """Old API keeps working and legacy 'vehicles'-shaped files still resolve."""
    from vehicle_registry import bind_vehicle, resolve_vehicle
    registry, base = bound
    bind_vehicle(tmp_path / "legacy.json", "ev", base, "2024.0", "rc-2", "4-motor")
    entry = resolve_vehicle(tmp_path / "legacy.json", "ev", "C:/CarSim2024.0_Prog")
    assert entry["run_control"] == "rc-2" and entry["powertrain"] == "4-motor"
    # a hand-written legacy registry (old JSON shape) resolves via resolve_base
    legacy = tmp_path / "handmade.json"
    legacy.write_text(json.dumps({"vehicles": {"old": {
        "base_run_all": str(base), "base_sha256": br.sha256(base),
        "carsim_version": "2024.0"}}}))
    assert br.resolve_base(legacy, "old", "C:/CarSim2024.0_Prog")["name"] == "old"
