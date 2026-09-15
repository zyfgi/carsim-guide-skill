"""P2 output/parameter discovery and structured override contracts."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import carsim_batch as cb
from carsim_errors import DatasetResolutionError, OutputChannelError
from output_registry import find_output_candidates, resolve_output_alias
from parameter_discovery import discover_parameter
from parameters import (
    RawOverride,
    ReferenceOverride,
    ScalarOverride,
    TableOverride,
    check_conflicts,
)
from scenario_schema import SimulationConfig
from validate_run import check_run


@pytest.fixture()
def discovery_db(tmp_path):
    spring = tmp_path / "Suspensions" / "FrontSpring.par"
    steer1 = tmp_path / "Steering" / "Rack.par"
    steer2 = tmp_path / "Steering" / "Column.par"
    spring.parent.mkdir()
    steer1.parent.mkdir()
    spring.write_text("#FullDataName Front suspension spring stiffness\n"
                      "FS_COMP_COEFFICIENT 27\nEND\n", encoding="utf-8")
    steer1.write_text("#FullDataName Steering stiffness rack\n"
                      "RACK_RATE 10\nEND\n", encoding="utf-8")
    steer2.write_text("#FullDataName Steering stiffness column\n"
                      "COLUMN_RATE 20\nEND\n", encoding="utf-8")
    return tmp_path


def test_output_alias_resolution():
    assert [item.name for item in resolve_output_alias("yaw rate")] == ["AVz"]
    assert resolve_output_alias("front suspension travel") == []


def test_unknown_output_not_guessed():
    assert find_output_candidates("engine flux capacitor") == []


def test_output_candidate_search(tmp_path):
    definition = tmp_path / "outputs.par"
    definition.write_text("front suspension travel WRT_Jounce_L1\n", encoding="utf-8")
    candidates = find_output_candidates("front suspension travel", [definition])
    assert [item.name for item in candidates] == ["Jounce_L1"]
    assert candidates[0].confidence == "weak" and candidates[0].spec is None


def test_subset_read_unknown_unrequested_channel(tmp_path):
    path = tmp_path / "run.csv"
    pd.DataFrame({"Time": [0, 1], "Vx": [36, 72],
                  "Unknown_Custom_Output": [1, 2]}).to_csv(path, index=False)
    frame = cb.read_run_csv(path, columns=["Time", "Vx"])
    assert frame.columns.tolist() == ["Time", "Vx"]
    assert frame.Vx.tolist() == [10, 20]


def test_full_read_unknown_channel(tmp_path):
    path = tmp_path / "run.csv"
    pd.DataFrame({"Time": [0], "Unknown_Custom_Output": [1]}).to_csv(path, index=False)
    with pytest.raises(OutputChannelError):
        cb.read_run_csv(path)


def test_parameter_registry_exact_match():
    report = discover_parameter("M_SU")
    assert report.resolved.keyword == "M_SU"
    assert report.candidates[0].confidence == "verified"


def test_parameter_alias():
    report = discover_parameter("sprung mass")
    assert report.resolved.keyword == "M_SU"
    assert "verified alias" in report.resolved.reason


def test_keyword_candidate_search(discovery_db):
    report = discover_parameter("FS_COMP_COEFFICIENT", discovery_db)
    assert len(report.candidates) == 1
    assert report.candidates[0].keyword == "FS_COMP_COEFFICIENT"
    assert report.resolved is None  # database hit is evidence, not verification


def test_ambiguous_parameter_not_auto_selected(discovery_db):
    report = discover_parameter("steering stiffness", discovery_db)
    assert {item.keyword for item in report.candidates} == {"RACK_RATE", "COLUMN_RATE"}
    assert report.resolved is None


def test_unresolved_parameter_returns_unresolved(discovery_db):
    report = discover_parameter("unobtainium compliance", discovery_db)
    assert report.unresolved and report.candidates == []


def test_table_override():
    table = TableOverride("TARGET_TABLE", [(0, 1), (1, 2)],
                          independent_variable="time")
    assert table.lines() == ["TARGET_TABLE LINEAR_FLAT", "0, 1", "1, 2", "ENDTABLE"]


def test_table_override_nonfinite():
    with pytest.raises(ValueError, match="finite"):
        TableOverride("TARGET_TABLE", [(0, 1), (1, float("nan"))])


def test_table_override_bad_shape():
    with pytest.raises(ValueError, match="shape"):
        TableOverride("TARGET_TABLE", [(0, 1), (1, 2, 3)])


def test_reference_override_resolves_dataset(discovery_db):
    ref = ReferenceOverride("PARSFILE", "Front suspension spring stiffness")
    assert ref.resolve(discovery_db).endswith("FrontSpring.par")


def test_reference_override_missing_dataset(discovery_db):
    with pytest.raises(DatasetResolutionError, match="missing"):
        ReferenceOverride("PARSFILE", "Missing dataset").resolve(discovery_db)
    with pytest.raises(DatasetResolutionError, match="not an arbitrary path"):
        ReferenceOverride("PARSFILE", "C:/outside/file.par")


def test_structured_overrides_integrate_with_compiler(discovery_db):
    text = cb.override_par(
        "base.par", 1.0, [(0, 10), (1, 10)], [(0, 0), (1, 0)],
        datadir=discovery_db,
        structured_overrides=[
            TableOverride("TARGET_TABLE", [(0, 1), (1, 2)]),
            ReferenceOverride("PARSFILE", "Front suspension spring stiffness"),
        ],
    )
    assert "TARGET_TABLE LINEAR_FLAT" in text
    assert "PARSFILE " + str(discovery_db / "Suspensions" / "FrontSpring.par") in text


def test_runtime_keyword_protected():
    with pytest.raises(ValueError, match="runtime"):
        check_conflicts([ScalarOverride("PRODUCT_VER", 2026)])
    with pytest.raises(ValueError, match="runtime"):
        RawOverride(["DLLFILE bad.dll"])
    # Port counts remain an explicit advanced-control escape hatch used by
    # the shipped Simulink/torque examples; they are not scalar parameters.
    assert RawOverride(["PORTS_IMP 1,4"]).lines() == ["PORTS_IMP 1,4"]


def test_scalar_echo_policy():
    assert ScalarOverride("M_SU", 1, "best_effort").echo_validation == "best_effort"
    with pytest.raises(ValueError, match="echo_validation"):
        ScalarOverride("M_SU", 1, "sometimes")


def test_scalar_echo_policy_controls_missing_echo(tmp_path):
    pd.DataFrame({"Time": [0.0, 0.1], "Vx": [0.0, 0.0]}).to_csv(
        tmp_path / "run.csv", index=False
    )
    (tmp_path / "run_echo.par").write_text("OTHER 1\n", encoding="utf-8")
    (tmp_path / "run_log.txt").write_text("synthetic", encoding="utf-8")
    best = check_run(
        tmp_path,
        SimulationConfig(0.1, 0.1),
        ["Vx"],
        expected_parameters={
            "M_SU": {"value": 1.0, "echo_validation": "best_effort"}
        },
    )
    assert best.passed and best.warnings()[0].code == "echo_absent"
    none = check_run(
        tmp_path,
        SimulationConfig(0.1, 0.1),
        ["Vx"],
        expected_parameters={"M_SU": {"value": 1.0, "echo_validation": "none"}},
    )
    assert none.passed and none.warnings() == []
