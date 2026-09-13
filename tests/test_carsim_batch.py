"""Pure-Python unit tests for carsim_batch.py (no CarSim needed).

Run: python -m pytest tests/ -q   (from the skill root)
Covers the generator formatting, the SI unit contract, and CSV reading
against a synthetic run.csv — the parts CI can verify without a solver.
"""
import logging
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import carsim_batch as cb  # noqa: E402


# ---------------------------------------------------------------- generators
def test_table_block_format():
    lines = cb._table("STEER_SW_TABLE", [(0.0, 0.0), (5.0, 12.5)])
    assert lines[0] == "STEER_SW_TABLE LINEAR_FLAT"
    assert lines[1] == "0.000000, 0.000000"
    assert lines[2] == "5.000000, 12.500000"
    assert lines[-1] == "ENDTABLE"


def test_dedupe_removes_repeated_x():
    assert cb._dedupe([(0, 1), (0.0, 2), (1e-10, 3), (1, 4)]) == [(0, 1), (1, 4)]


def test_override_par_contains_core_switches():
    txt = cb.override_par("C:/b/Run_all.par", 65.0,
                          [(0, 50), (65, 50)], [(0, 0), (65, 0)],
                          extra_lines=["M_SU 1254.0"])
    for needle in ("PARSFILE C:/b/Run_all.par", "OPT_ERROR_DIALOG 0",
                   "OPT_VS_FILETYPE 4", "TSTEP 0.0010000",
                   "SPEED_TARGET_TABLE LINEAR_FLAT", "STEER_SW_TABLE LINEAR_FLAT",
                   "MU_ROAD_CARPET 2D_STEP", "M_SU 1254.0",
                   "WRT_Vx", "END"):
        assert needle in txt, needle
    # extra_lines must land after the tables, before the WRT block
    assert txt.index("M_SU 1254.0") > txt.index("ENDTABLE")


def test_simfile_pins_64bit_and_ports():
    txt = cb.simfile("C:/work/demo", "C:/CarSim/ProG", "C:/CarSim/Data")
    assert "carsim_64.dll" in txt and "carsim_32" not in txt
    assert "PORTS_IMP 0" in txt and "PORTS_EXP 0" in txt
    assert txt.startswith("SIMFILE") and "\nEND" in txt


# ---------------------------------------------------------------- unit scale
@pytest.mark.parametrize("col,factor", [
    ("Time", 1.0), ("Vx", 0.2777778), ("Vy", 0.2777778),
    ("Ax", 9.81), ("Ay", 9.81), ("AVz", 0.0174533),
    ("Roll", 0.0174533), ("Steer_L1", 0.0174533), ("Alpha_R2", 0.0174533),
    ("AVy_L1", 0.1047198),           # wheel speed: rpm -> rad/s
    ("Fx_L1", 1.0), ("My_Bk_R2", 1.0), ("Kappa_L1", 1.0),  # already SI / -1
])
def test_si_scale(col, factor):
    assert cb.si_scale(col) == pytest.approx(factor, rel=1e-3)


def test_known_unit_categories():
    assert cb._known_unit("Fx_L1") and cb._known_unit("My_Dr_R2")
    assert cb._known_unit("Kappa_L1") and cb._known_unit("AV_Mt_D1_L")
    assert not cb._known_unit("Vx") and not cb._known_unit("Weird_Column")


# ---------------------------------------------------------------- csv reader
@pytest.fixture()
def synthetic_csv(tmp_path):
    p = tmp_path / "run.csv"
    p.write_text(
        "Time,Vx,Ax,AVz,Fz_L1,Lat_Veh,Madeup_Channel\n"
        "0.0,50.0,0.10,5.0,3200.0,1.0,7.0\n"
        "1.0,50.0,0.10,5.0,3200.0,1.0,7.0\n", encoding="utf-8")
    return str(p)


def test_read_run_csv_converts_to_si(synthetic_csv):
    df = cb.read_run_csv(synthetic_csv)
    assert df.Vx.iloc[0] == pytest.approx(50 * 0.2777778, rel=1e-3)
    assert df.Ax.iloc[0] == pytest.approx(0.981, rel=1e-3)
    assert df.AVz.iloc[0] == pytest.approx(5 * 0.0174533, rel=1e-3)
    assert df.Fz_L1.iloc[0] == pytest.approx(3200.0)  # already SI


def test_read_run_csv_drops_unreliable(synthetic_csv):
    df = cb.read_run_csv(synthetic_csv)
    assert "Lat_Veh" not in df.columns


def test_read_run_csv_respects_order_and_warns_unknown(synthetic_csv, caplog):
    with caplog.at_level(logging.WARNING):
        df = cb.read_run_csv(synthetic_csv, columns=["Time", "Vx", "AVz"])
    assert list(df.columns) == ["Time", "Vx", "AVz"]
    assert not any("Madeup_Channel" in r.getMessage() for r in caplog.records)
    # unknown column warning fires when it IS loaded
    with caplog.at_level(logging.WARNING):
        cb.read_run_csv(synthetic_csv)
    assert any("Madeup_Channel" in r.getMessage() for r in caplog.records)
