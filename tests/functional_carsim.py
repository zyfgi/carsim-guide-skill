"""Solver-in-loop functional checks for carsim_batch.py (need a real CarSim).

Run:  python -m pytest tests/functional_carsim.py -v

Needs CarSim install paths (CARSIM_PROG / CARSIM_DATADIR / CARSIM_BASE env
vars, or run scripts/setup_paths.py once - its cache is picked up
automatically) and a license (CarSim GUI open, or cslm.exe running). Without
paths every test skips, so plain CI stays green. Set CARSIM_MATLAB=<path to
matlab.exe> to also run the Simulink co-simulation end-to-end check.

Unlike tests/test_carsim_batch.py (pure formatting/unit-contract checks),
these assert PHYSICS against the real solver: a constant per-wheel torque
import must actually spin the wheels, an open-loop throttle/brake profile
must accelerate then decelerate, and a speed-table override must REPLACE the
base table in the run echo. Each test runs into its own temp directory.
"""
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import carsim_batch as cb  # noqa: E402


def _available_paths():
    try:
        return cb.resolve_paths()
    except RuntimeError:
        return None


PATHS = _available_paths()
pytestmark = pytest.mark.skipif(
    PATHS is None, reason="no CarSim paths (env vars or setup_paths.py "
                          "cache) - skipping solver-in-loop checks")


def _run_scenario(tmp_path, name, tstop, speed_rows, steer_rows, extra_lines,
                  timeout=600):
    sim = cb.make_scenario(str(tmp_path / name), PATHS[2], PATHS[0], PATHS[1],
                           tstop, speed_rows, steer_rows,
                           unsafe_extra_lines=extra_lines)
    cb.run_solver(sim, timeout=timeout)
    return Path(tmp_path / name)


def _echo_table_rows(echo_path, keyword):
    """Rows (float pairs) of the first <keyword> ... ENDTABLE block in an echo."""
    text = Path(echo_path).read_text(errors="replace")
    m = re.search(r"^%s\b(.*?)^ENDTABLE" % re.escape(keyword), text,
                  re.S | re.M)
    if not m:
        return None
    rows = []
    for line in m.group(1).splitlines():
        nums = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)
        if len(nums) >= 2:
            rows.append([float(n) for n in nums[:2]])
    return rows


def test_constant_torque_import_spins_wheels(tmp_path):
    """4 x 150 N.m wheel-torque import (VS_REPLACE form, PORTS_IMP 0) must
    accelerate the car from standstill: Vx clearly > 0 and My_Dr tracks the
    command (verified 1:1) - references/advanced-controls.md section 2."""
    d = _run_scenario(
        tmp_path, "torque", 6.0,
        [(0, 0), (6, 0)], [(0, 0), (6, 0)],
        ["OPT_SC 0",
         "IMPORT IMP_M_MOTOR_CMD_D1_L VS_REPLACE 150",
         "IMPORT IMP_M_MOTOR_CMD_D1_R VS_REPLACE 150",
         "IMPORT IMP_M_MOTOR_CMD_D2_L VS_REPLACE 150",
         "IMPORT IMP_M_MOTOR_CMD_D2_R VS_REPLACE 150",
         "PORTS_IMP 0"])
    df = cb.read_run_csv(str(d / "run.csv"),
                         columns=["Time", "Vx", "Ax", "My_Dr_L1"])
    assert df.Vx.iloc[-1] > 5.0, "car did not spin up: Vx_end=%.2f m/s" \
        % df.Vx.iloc[-1]
    assert df.My_Dr_L1.iloc[-1] == pytest.approx(150.0, rel=0.05)
    # Ax > 0.3 m/s^2 catches the "import parsed but inert" regression (the
    # documented VS_REPLACE-with-active-ports trap) without hard-coding a
    # vehicle-specific acceleration level
    assert df.Ax[df.Time.between(1.0, 3.0)].mean() > 0.3


def test_openloop_throttle_then_brake(tmp_path):
    """OPT_SC 0 + THROTTLE_ENGINE_TABLE then PBK_CON_TABLE: accelerate ~6 s,
    then brake pressure must cut speed to under half (event-style open-loop
    driving) - references/advanced-controls.md section 1."""
    d = _run_scenario(
        tmp_path, "openloop", 12.0,
        [(0, 0), (12, 0)], [(0, 0), (12, 0)],
        ["OPT_SC 0",
         "THROTTLE_ENGINE_TABLE LINEAR_FLAT",
         "0, 1", "6, 1", "ENDTABLE",
         "PBK_CON_TABLE LINEAR_FLAT",
         "0, 0", "6.2, 0", "6.5, 15.0", "12, 15.0", "ENDTABLE"])
    df = cb.read_run_csv(str(d / "run.csv"), columns=["Time", "Vx", "Ax"])
    v6 = df.Vx[df.Time.between(5.5, 6.0)].mean()
    assert v6 > 3.0, "throttle did not accelerate: Vx(6s)=%.2f m/s" % v6
    assert df.Vx.iloc[-1] < 0.5 * v6, "brake did not slow the car"


def test_speed_table_override_replaces_base(tmp_path):
    """A non-constant SPEED_TARGET_TABLE override must REPLACE the base table:
    run_echo.par shows exactly the override's rows (append would show base
    rows too) - references/advanced-controls.md section 3."""
    d = _run_scenario(tmp_path, "table", 10.0,
                      [(0, 23.4), (10, 46.8)], [(0, 0), (10, 0)], [])
    rows = _echo_table_rows(d / "run_echo.par", "SPEED_TARGET_TABLE")
    assert rows is not None, "speed table missing from run_echo.par"
    assert len(rows) == 2, "expected exactly 2 rows (REPLACE), got %d" % len(rows)
    assert rows[0][1] == pytest.approx(23.4, rel=1e-3)
    assert rows[1][1] == pytest.approx(46.8, rel=1e-3)


@pytest.mark.skipif(not os.environ.get("CARSIM_MATLAB"),
                    reason="CARSIM_MATLAB not set - skipping Simulink check")
def test_simulink_cosim_end_to_end(tmp_path):
    """Full Simulink + CarSim closed loop via examples/simulink_cosim.py
    (needs MATLAB + Simulink; ~2-10 min). CARSIM_MATLAB = path to matlab.exe."""
    root = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, str(root / "examples" / "simulink_cosim.py"),
           "--out", str(tmp_path / "cosim"),
           "--matlab", os.environ["CARSIM_MATLAB"]]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2400,
                          encoding="utf-8", errors="replace")
    tail = (proc.stdout or "")[-1500:] + (proc.stderr or "")[-1500:]
    assert proc.returncode == 0, "simulink_cosim.py failed:\n%s" % tail
    assert "PASS" in proc.stdout, "no PASS verdict:\n%s" % tail
