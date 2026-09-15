"""P2 control, diagnostics and version compatibility contracts."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from control_modes import ControlSpec, select_external_mode
from diagnostics import diagnose_run
from scenario_schema import VehicleOverrides
from version_compatibility import (
    compatibility_status,
    parse_version,
    supports,
)


def _run_dir(tmp_path, started=None):
    root = tmp_path / "run"
    root.mkdir()
    (root / "override.par").write_text("WRT_Vx\nEND\n")
    (root / "simfile.sim").write_text("DLLFILE C:/x/carsim_64.dll\nEND\n")
    manifest = {"run": {"started_utc": started}, "carsim": {},
                "scenario": {"parameters": [{"keyword": "M_SU", "value": 10}]}}
    (root / "run_manifest.json").write_text(json.dumps(manifest))
    return root, manifest


def test_control_modes_keep_target_and_actuator_distinct():
    target = ControlSpec("driver_internal", "driver", "speed_target")
    actuator = ControlSpec("simulink_external", "controller", "throttle_command",
                           "IMP_THROTTLE", True)
    assert target.semantic != actuator.semantic
    assert select_external_mode(True) == "simulink_external"
    assert select_external_mode(False) == "predefined_table"
    with pytest.raises(ValueError, match="Runtime feedback"):
        ControlSpec("predefined_table", "csv", "wheel_torque_command",
                    requires_closed_loop=True)


def test_diagnostic_missing_solver(tmp_path):
    root, manifest = _run_dir(tmp_path)
    manifest["carsim"]["solver"] = str(tmp_path / "missing.exe")
    (root / "run_manifest.json").write_text(json.dumps(manifest))
    result = diagnose_run(root)
    assert any(item.code == "solver_missing" for item in result.diagnostics)


def test_diagnostic_stale_csv(tmp_path):
    started = datetime.now(timezone.utc) + timedelta(hours=1)
    root, _ = _run_dir(tmp_path, started.isoformat())
    pd.DataFrame({"Time": [0], "Vx": [0]}).to_csv(root / "run.csv", index=False)
    (root / "run_echo.par").write_text("M_SU 10\n")
    result = diagnose_run(root)
    assert any(item.code == "run_csv_stale" for item in result.diagnostics)


def test_diagnostic_missing_termination(tmp_path):
    root, _ = _run_dir(tmp_path)
    pd.DataFrame({"Time": [0], "Vx": [0]}).to_csv(root / "run.csv", index=False)
    (root / "run_echo.par").write_text("M_SU 10\n")
    (root / "solver_stdout.txt").write_text("solver started")
    result = diagnose_run(root)
    assert any(item.code == "termination_missing" for item in result.diagnostics)


def test_diagnostic_echo_mismatch(tmp_path):
    root, _ = _run_dir(tmp_path)
    pd.DataFrame({"Time": [0], "Vx": [0]}).to_csv(root / "run.csv", index=False)
    (root / "run_echo.par").write_text("M_SU 11\n")
    result = diagnose_run(root)
    assert any(item.code == "echo_mismatch" for item in result.diagnostics)


def test_version_parse():
    version = parse_version("C:/CarSim/CarSim2026.2_Prog")
    assert (version.major, version.minor, version.key) == (2026, 2, "2026.2")


def test_verified_version():
    status = compatibility_status("2024.0")
    assert status.verified and supports("cli_solver", "2024.0")


def test_unverified_version_warning():
    status = compatibility_status("2026.1")
    assert not status.verified and "attempting" in status.warning


def test_vehicle_override_error_uses_field_name():
    with pytest.raises(ValueError, match="sprung_mass_kg"):
        VehicleOverrides(sprung_mass_kg=-1)
