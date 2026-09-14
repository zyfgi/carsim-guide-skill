"""Unit tests for scripts/setup_paths.py (pure filesystem, no CarSim needed).

Run: python -m pytest tests/ -q   (from the skill root)
Builds a fake CarSim install tree in tmp_path and checks discovery, the
on-disk cache, the --json / --set / --forget commands, and stale-cache
validation. The cache location is redirected via CARSIM_GUIDE_CONFIG, so the
developer's real ~/.carsim_guide_paths.json is never touched.
"""
import json
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import setup_paths as sp  # noqa: E402


@pytest.fixture()
def fake_install(tmp_path, monkeypatch):
    """Fake install: Prog with CLI+DLL+cslm, a _Data copy and a _Data_test."""
    prog = tmp_path / "CarSim2024.0_Prog"
    (prog / "Programs" / "solvers").mkdir(parents=True)
    (prog / "Programs" / "VS_SolverWrapper_CLI_64.exe").write_text("")
    (prog / "Programs" / "solvers" / "carsim_64.dll").write_text("")
    (prog / "Programs" / "cslm.exe").write_text("")

    data = tmp_path / "CarSim2024.0_Data"
    older = data / "Results" / "Run_aaaa"
    older.mkdir(parents=True)
    (older / "Run_all.par").write_text("PARSFILE\nEND\n")

    test_data = tmp_path / "CarSim2024.0_Data_test"
    newer = test_data / "Results" / "Run_bbbb"
    newer.mkdir(parents=True)
    (newer / "Run_all.par").write_text("PARSFILE\nEND\n")

    os.utime(older / "Run_all.par", (1e6, 1e6))   # old
    os.utime(newer / "Run_all.par", (2e9, 2e9))   # newest -> default base

    cfg_file = tmp_path / "paths.json"
    monkeypatch.setenv(sp.CONFIG_ENV, str(cfg_file))
    return {"prog": prog, "data": data, "newest": newer / "Run_all.par",
            "cfg": cfg_file}


def test_discover_finds_prog_primary_data_and_newest_base(fake_install):
    cfg = sp.discover(search_dirs=[str(fake_install["prog"].parent)])
    assert cfg["prog"] == str(fake_install["prog"].resolve())
    assert cfg["datadir"] == str(fake_install["data"].resolve())
    assert cfg["base_run_all"] == str(fake_install["newest"].resolve())
    # newest base wins even when it lives in a *_Data_test copy
    assert "_Data_test" in cfg["base_run_all"]
    assert any(fake_install["data"].name in b for b in cfg["other_bases"])
    assert cfg["cli_solver"].endswith("VS_SolverWrapper_CLI_64.exe")
    assert cfg["solver_dll"].endswith("carsim_64.dll")
    assert cfg["license_manager"].endswith("cslm.exe")


def test_save_load_roundtrip(fake_install):
    cfg = sp.discover(search_dirs=[str(fake_install["prog"].parent)])
    sp.save_config(cfg)
    assert sp.load_config() == cfg


def test_cli_json_then_forget(fake_install, capsys):
    assert sp.main(["--json"]) == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["prog"].endswith("CarSim2024.0_Prog")
    assert payload["base_run_all"].endswith("Run_all.par")
    assert sp.main(["--forget"]) == 0
    assert not fake_install["cfg"].exists()


def test_validate_flags_missing_paths(fake_install):
    cfg = sp.discover(search_dirs=[str(fake_install["prog"].parent)])
    assert sp._validate(cfg) is True
    cfg["prog"] = "Z:/gone/CarSim2024.0_Prog"
    assert sp._validate(cfg) is False


def test_set_bootstraps_manual_install(tmp_path, monkeypatch, capsys):
    """A non-standard install (discovery fails) can still be pinned by hand;
    dependents (cli/dll/datadir) are derived from prog."""
    monkeypatch.setenv(sp.CONFIG_ENV, str(tmp_path / "paths.json"))

    def _no_install(*a, **k):
        raise SystemExit("no CarSim install found")

    monkeypatch.setattr(sp, "discover", _no_install)
    prog = tmp_path / "CarSimX_Prog"
    (prog / "Programs" / "solvers").mkdir(parents=True)
    (prog / "Programs" / "VS_SolverWrapper_CLI_64.exe").write_text("")
    (prog / "Programs" / "solvers" / "carsim_64.dll").write_text("")
    (tmp_path / "CarSimX_Data").mkdir()          # sibling => datadir resolved
    assert sp.main(["--set", "prog=%s" % prog]) == 0
    cfg = sp.load_config()
    assert cfg["prog"] == str(prog.resolve())
    assert cfg["cli_solver"].endswith("VS_SolverWrapper_CLI_64.exe")
    assert cfg["solver_dll"].endswith("carsim_64.dll")
    assert cfg["datadir"].endswith("CarSimX_Data")


def test_set_rejects_unknown_key(tmp_path, monkeypatch):
    monkeypatch.setenv(sp.CONFIG_ENV, str(tmp_path / "paths.json"))
    with pytest.raises(SystemExit, match="--set keys"):
        sp.main(["--set", "nonsense=1"])
