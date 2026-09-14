"""P1 database_tools (read-only exploration) + parameters (scalar overrides).

Uses a temporary synthetic database fixture; never touches a real CarSim.
"""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import database_tools as dt  # noqa: E402
from parameters import (PARAMETER_REGISTRY, PROTECTED_KEYWORDS,  # noqa: E402
                        ScalarOverride, check_conflicts, coerce_scalar_overrides)


@pytest.fixture()
def db(tmp_path):
    """Synthetic CarSim-like database: two libraries, links, keyword lines."""
    sprung = tmp_path / "Vehicles" / "Sprung_Mass"
    susp = tmp_path / "Suspensions"
    sprung.mkdir(parents=True)
    susp.mkdir(parents=True)
    (sprung / "Vehicle_abc.par").write_text(
        "#FileID vehicle-abc-uuid\n"
        "#DataSet C-Class Hatchback EV\n"
        "#Category Vehicles\n"
        "#FullDataName C-Class Hatchback EV (AWD)\n"
        "PARSFILE\n"
        "PARSFILE {susp}/Compliance_Front_Spring.par\n"
        "M_SU 1234.0\n"
        "END\n".replace("{susp}", str(susp)), encoding="utf-8")
    (susp / "Compliance_Front_Spring.par").write_text(
        "#FullDataName Front Coil Spring 27 N/mm\n"
        "PARSFILE\n"
        "FS_COMP_COEFFICIENT 27\n"
        "FS_EXT_COEFFICIENT 27\n"
        "END\n", encoding="utf-8")
    (tmp_path / "Roads").mkdir()
    (tmp_path / "Roads" / "Road_Skidpad.par").write_text(
        "#FullDataName Skidpad Pad Road\n"
        "MU 0.85\n"
        "END\n", encoding="utf-8")
    echo = tmp_path / "run_echo.par"
    echo.write_text("M_SU 1254.0 ! sprung mass kg\n"
                    "Y_CG_SU 150.0\n", encoding="utf-8")
    return tmp_path, echo


# ---------------------------------------------------------------- parameters
def test_parameter_registry_is_verified_only():
    assert set(PARAMETER_REGISTRY) == {"M_SU", "LX_CG_SU", "Y_CG_SU",
                                       "H_CG_SU", "IZZ_SU"}
    assert PARAMETER_REGISTRY["M_SU"].native_unit == "kg"


def test_scalar_override_validation():
    line = ScalarOverride("FS_COMP_COEFFICIENT", 29.7).lines()
    assert line == ["FS_COMP_COEFFICIENT 29.7"]
    with pytest.raises(ValueError, match="keyword"):
        ScalarOverride("BAD KEYWORD", 1.0)
    with pytest.raises(ValueError, match="keyword"):
        ScalarOverride("", 1.0)
    with pytest.raises(ValueError, match="finite"):
        ScalarOverride("M_SU", float("inf"))


def test_scalar_override_coerce_and_conflicts():
    items = coerce_scalar_overrides([("M_SU", 1250.0),
                                     {"keyword": "IZZ_SU", "value": 1700.0}])
    assert [o.keyword for o in items] == ["M_SU", "IZZ_SU"]
    check_conflicts(items)  # vehicle parameters are never protected
    with pytest.raises(ValueError, match="conflicts"):
        check_conflicts(coerce_scalar_overrides([("TSTEP", 0.002)]))
    with pytest.raises(ValueError, match="conflicts"):
        check_conflicts(coerce_scalar_overrides([("OPT_VS_FILETYPE", 4)]))
    with pytest.raises(ValueError, match="conflicts"):
        check_conflicts(coerce_scalar_overrides([("MY_PARAMETER", 1)]),
                        protected=["my_parameter"])
    assert "TSTOP" in PROTECTED_KEYWORDS


def test_override_par_integrates_scalar_overrides():
    import carsim_batch as cb
    txt = cb.override_par("C:/b/Run_all.par", 10.0, [(0, 50), (10, 50)],
                          [(0, 0), (10, 0)],
                          scalar_overrides=[("FS_COMP_COEFFICIENT", 29.7)])
    assert "FS_COMP_COEFFICIENT 29.7" in txt
    assert txt.index("FS_COMP_COEFFICIENT") > txt.index("ENDTABLE")
    assert txt.index("FS_COMP_COEFFICIENT") < txt.index("WRT_Vx")
    with pytest.raises(ValueError, match="conflicts"):
        cb.override_par("C:/b/Run_all.par", 10.0, [(0, 50), (10, 50)],
                        [(0, 0), (10, 0)], scalar_overrides=[("TSTEP", 0.002)])


# ------------------------------------------------------------- database tools
def test_find_dataset_by_full_name(db):
    datadir, _ = db
    hits = dt.find_datasets(datadir, "c-class")
    assert len(hits) == 1 and hits[0]["library"] == "Vehicles"
    assert "Hatchback" in hits[0]["full_data_name"]
    assert dt.find_datasets(datadir, "spring")[0]["library"] == "Suspensions"
    assert dt.find_datasets(datadir, "no-such-thing") == []


def test_get_dataset_identity(db):
    datadir, _ = db
    identity = dt.get_dataset_identity(datadir / "Vehicles" / "Sprung_Mass" / "Vehicle_abc.par")
    assert identity["FullDataName"].startswith("C-Class")
    assert identity["Category"] == "Vehicles"


def test_parse_parsfile_links(db):
    datadir, _ = db
    links = dt.get_parsfile_links(datadir / "Vehicles" / "Sprung_Mass" / "Vehicle_abc.par")
    assert links[0]["raw"] == "PARSFILE" or links[0]["raw"] != ""
    target = [l for l in links if "Compliance" in l["raw"]][0]
    assert target["exists"] is True
    missing = dt.get_parsfile_links(datadir / "Roads" / "Road_Skidpad.par")
    assert missing == []


def test_resolve_tree_cycle_safe(tmp_path):
    a = tmp_path / "a.par"
    b = tmp_path / "b.par"
    a.write_text("PARSFILE %s\nEND\n" % b.resolve())
    b.write_text("PARSFILE %s\nEND\n" % a.resolve())
    tree = dt.resolve_dataset_tree(a, max_depth=5)
    assert tree["identity"] == {} or isinstance(tree["identity"], dict)
    child = tree["links"][0]
    assert child["links"][0]["cycle"] is True  # loop detected, no recursion
    with pytest.raises(ValueError, match="Not a dataset"):
        dt.resolve_dataset_tree(tmp_path / "missing.par")


def test_find_keyword(db):
    datadir, _ = db
    hits = dt.find_keyword(datadir, "FS_COMP_COEFFICIENT")
    assert len(hits) == 1
    assert hits[0]["count"] == 1 and hits[0]["first_line"] == "FS_COMP_COEFFICIENT 27"
    assert "Front Coil Spring" in hits[0]["full_data_name"]
    su_hits = dt.find_keyword(datadir, "M_SU")
    assert any(h["library"] == "Vehicles" for h in su_hits)  # echo file matches too


def test_search_database_text(db):
    datadir, _ = db
    hits = dt.search_database_text(datadir, "skidpad")
    assert hits and hits[0]["line_number"] == 1
    assert dt.search_database_text(datadir, "SKIDPAD")[0]["path"] == hits[0]["path"]


def test_inspect_echo_keyword(db):
    _, echo = db
    rows = dt.inspect_echo_keyword(echo, "M_SU")
    assert rows[0]["value"] == 1254.0
    assert rows[0]["comment"] == "sprung mass kg"
    assert dt.inspect_echo_keyword(echo, "Y_CG_SU")[0]["value"] == 150.0
    assert dt.inspect_echo_keyword(echo, "NOT_PRESENT") == []


def test_database_tools_are_read_only(db):
    datadir, echo = db

    def snapshot():
        return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in datadir.rglob("*") if p.is_file()}

    before = snapshot()
    dt.find_datasets(datadir, "spring")
    dt.find_keyword(datadir, "M_SU")
    dt.search_database_text(datadir, "0.85")
    dt.get_dataset_identity(datadir / "Vehicles" / "Sprung_Mass" / "Vehicle_abc.par")
    dt.resolve_dataset_tree(datadir / "Vehicles" / "Sprung_Mass" / "Vehicle_abc.par", datadir)
    dt.inspect_echo_keyword(echo, "M_SU")
    assert snapshot() == before
