"""Pure-Python unit tests for carsim_batch.py (no CarSim needed).

Run: python -m pytest tests/ -q   (from the skill root)
Covers the generator formatting, the SI unit contract, and CSV reading
against a synthetic run.csv — the parts CI can verify without a solver.
"""
import json
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
    assert lines[1] == "0, 0"
    assert lines[2] == "5, 12.5"
    assert lines[-1] == "ENDTABLE"


def test_dedupe_removes_repeated_x():
    assert cb._dedupe([(0, 1), (0.0, 2), (1e-10, 3), (1, 4)]) == [(0, 1), (1, 4)]


def test_override_par_contains_core_switches():
    txt = cb.override_par("C:/b/Run_all.par", 65.0,
                          [(0, 50), (65, 50)], [(0, 0), (65, 0)],
                          unsafe_extra_lines=["M_SU 1254.0"])
    for needle in ("PARSFILE C:/b/Run_all.par", "OPT_ERROR_DIALOG 0",
                   "OPT_VS_FILETYPE 4", "TSTEP 0.001",
                   "SPEED_TARGET_TABLE LINEAR_FLAT", "STEER_SW_TABLE LINEAR_FLAT",
                   "MU_ROAD_CARPET 2D_STEP", "M_SU 1254.0",
                   "WRT_Vx", "END"):
        assert needle in txt, needle
    # extra_lines must land after the tables, before the WRT block
    assert txt.index("M_SU 1254.0") > txt.index("ENDTABLE")


def test_simfile_pins_64bit_and_ports():
    txt = cb.simfile("C:/work/demo", "C:/CarSim/ProG", "C:/CarSim/Data", product_version="2024.0")
    assert "carsim_64.dll" in txt and "carsim_32" not in txt
    assert "PORTS_IMP 0" in txt and "PORTS_EXP 0" in txt
    for line in txt.splitlines():
        if line.startswith(("PROGDIR ", "DATADIR ")):
            assert line.endswith(("/", "\\"))
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
    assert cb._known_unit("Vx") and not cb._known_unit("Weird_Column")


def test_si_scale_never_matches_across_word_boundaries():
    # exact / underscore-delimited matching only: an "avy" rule must not
    # silently rescale unrelated names like AVYX or AV_Trans (review round 2)
    assert cb.si_scale("AVYX") == 1.0
    assert cb.si_scale("AV_Trans") == 1.0
    assert cb.si_scale("Vx_R1") == pytest.approx(0.2777778, rel=1e-3)


# ------------------------------------------------------- install-path cache
def test_resolve_paths_precedence_arg_env_then_cache(tmp_path, monkeypatch):
    cache = tmp_path / "paths.json"
    base = tmp_path / "Run_all.par"
    base.write_text("PARSFILE\nEND\n")
    cache.write_text(json.dumps({
        "prog": "C:/cache/Prog", "datadir": "C:/cache/Data",
        "base_run_all": str(base), "base_selection": "explicit", "base_sha256": cb.sha256(base)}))
    monkeypatch.setenv(cb.CONFIG_ENV, str(cache))
    for var in ("CARSIM_PROG", "CARSIM_DATADIR", "CARSIM_BASE"):
        monkeypatch.delenv(var, raising=False)

    assert cb.resolve_paths() == ("C:/cache/Prog", "C:/cache/Data",
                                  str(base))
    monkeypatch.setenv("CARSIM_PROG", "C:/env/Prog")
    assert cb.resolve_paths()[0] == "C:/env/Prog"          # env beats cache
    assert cb.resolve_paths(prog="C:/arg/Prog")[0] == "C:/arg/Prog"  # arg wins
    # run_solver only needs prog: with datadir/base not required, the env-var
    # prog alone satisfies resolution even without a cache
    monkeypatch.delenv(cb.CONFIG_ENV, raising=False)
    p, _, _ = cb.resolve_paths(require=("prog",))
    assert p == "C:/env/Prog"


def test_resolve_paths_missing_raises_with_setup_hint(tmp_path, monkeypatch):
    monkeypatch.setenv(cb.CONFIG_ENV, str(tmp_path / "missing.json"))
    for var in ("CARSIM_PROG", "CARSIM_DATADIR", "CARSIM_BASE"):
        monkeypatch.delenv(var, raising=False)
    with pytest.raises(RuntimeError, match="setup_paths\\.py"):
        cb.resolve_paths()


# ---------------------------------------------------------------- csv reader
@pytest.fixture()
def synthetic_csv(tmp_path):
    p = tmp_path / "run.csv"
    p.write_text(
        "Time,Vx,Ax,AVz,Fz_L1,Lat_Veh,AV_Mt_D1_L\n"
        "0.0,50.0,0.10,5.0,3200.0,1.0,60.0\n"
        "1.0,50.0,0.10,5.0,3200.0,1.0,60.0\n", encoding="utf-8")
    return str(p)


def test_read_run_csv_converts_to_si(synthetic_csv):
    df = cb.read_run_csv(synthetic_csv)
    assert df.Vx.iloc[0] == pytest.approx(50 * 0.2777778, rel=1e-3)
    assert df.Ax.iloc[0] == pytest.approx(0.981, rel=1e-3)
    assert df.AVz.iloc[0] == pytest.approx(5 * 0.0174533, rel=1e-3)
    assert "Fz_L1" not in df  # default reader cannot leak truth
    assert cb.read_run_csv(synthetic_csv, allow_truth=True).Fz_L1.iloc[0] == 3200


def test_read_run_csv_drops_unreliable(synthetic_csv):
    df = cb.read_run_csv(synthetic_csv)
    assert "Lat_Veh" not in df.columns


def test_read_run_csv_respects_order_and_rejects_unknown(synthetic_csv, tmp_path):
    df = cb.read_run_csv(synthetic_csv, columns=["Time", "Vx", "AVz"])
    assert list(df.columns) == ["Time", "Vx", "AVz"]
    unknown = tmp_path / "unknown.csv"
    unknown.write_text("Time,Madeup_Channel\n0,7\n")
    with pytest.raises(ValueError, match="Unregistered"):
        cb.read_run_csv(unknown)
