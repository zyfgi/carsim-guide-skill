"""P2.1 fail-closed discovery, containment, and evidence-state regressions."""

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import database_tools as database
from output_registry import (
    OUTPUT_REGISTRY,
    find_output_candidates,
    normalize_output_query,
)
from override_registry import VerificationLevel
from parameter_discovery import discover_parameter, normalize_parameter_query
from parameters import (
    PARAMETER_REGISTRY,
    ReferenceOverride,
    ScalarOverride,
    TableOverride,
)
from scenario_schema import SimulationConfig
from validate_run import check_run


@pytest.fixture()
def discovery_artifacts(tmp_path):
    output = tmp_path / "output_definition.par"
    output.write_text(
        "front suspension vertical travel WRT_Jounce_L1\n"
        "steering wheel angle WRT_Steer_SW\n"
        "engine speed WRT_Engine_RPM\n",
        encoding="utf-8",
    )
    database_root = tmp_path / "Database"
    (database_root / "Suspensions").mkdir(parents=True)
    (database_root / "Steering").mkdir()
    (database_root / "Suspensions" / "spring.par").write_text(
        "#FullDataName Front suspension spring stiffness\n"
        "FS_COMP_COEFFICIENT 27\nEND\n",
        encoding="utf-8",
    )
    (database_root / "Steering" / "rack.par").write_text(
        "#FullDataName Steering stiffness rack\nRACK_RATE 10\nEND\n",
        encoding="utf-8",
    )
    (database_root / "Steering" / "column.par").write_text(
        "#FullDataName Steering stiffness column\nCOLUMN_RATE 20\nEND\n",
        encoding="utf-8",
    )
    return output, database_root


@pytest.mark.parametrize(
    ("query", "channel"),
    [
        ("前悬架垂向行程", "Jounce_L1"),
        ("方向盘转角", "Steer_SW"),
        ("发动机转速", "Engine_RPM"),
    ],
)
def test_multilingual_output_discovery_uses_literal_artifact_evidence(
    discovery_artifacts, query, channel
):
    output, _ = discovery_artifacts
    candidates = find_output_candidates(query, artifacts=[output])
    assert [candidate.channel for candidate in candidates] == [channel]
    assert candidates[0].verification_state == "artifact_match"
    assert candidates[0].matched_text and candidates[0].reason


def test_output_empty_search_terms_never_match_all(discovery_artifacts):
    output, _ = discovery_artifacts
    assert normalize_output_query("未知中文量", []).search_terms == ()
    assert find_output_candidates("未知中文量", artifacts=[output]) == []
    assert find_output_candidates("未知中文量", search_terms=[], artifacts=[output]) == []


def test_output_discovery_does_not_pollute_registry(discovery_artifacts):
    output, _ = discovery_artifacts
    before = dict(OUTPUT_REGISTRY)
    find_output_candidates("前悬架垂向行程", artifacts=[output])
    assert OUTPUT_REGISTRY == before and "Jounce_L1" not in OUTPUT_REGISTRY


def test_chinese_parameter_query_with_terms_requires_database_evidence(
    discovery_artifacts,
):
    _, root = discovery_artifacts
    report = discover_parameter(
        "前悬架弹簧刚度",
        root,
        search_terms=["front suspension spring stiffness"],
    )
    assert [candidate.keyword for candidate in report.candidates] == [
        "FS_COMP_COEFFICIENT"
    ]
    assert report.resolved is None
    assert report.candidates[0].dataset_path


def test_chinese_parameter_default_terms_and_empty_terms(discovery_artifacts):
    _, root = discovery_artifacts
    report = discover_parameter("前悬架弹簧刚度", root)
    assert {candidate.keyword for candidate in report.candidates} == {
        "FS_COMP_COEFFICIENT"
    }
    empty = discover_parameter("未知刚度", root, search_terms=[])
    assert empty.unresolved and empty.candidates == []
    assert normalize_parameter_query("未知刚度", []).search_terms == ()


def test_parameter_ambiguity_and_registry_immutability(discovery_artifacts):
    _, root = discovery_artifacts
    before = dict(PARAMETER_REGISTRY)
    report = discover_parameter("转向系统刚度", root)
    assert {candidate.keyword for candidate in report.candidates} == {
        "RACK_RATE",
        "COLUMN_RATE",
    }
    assert report.resolved is None
    assert PARAMETER_REGISTRY == before


@pytest.fixture()
def external_graph(tmp_path):
    datadir = tmp_path / "Database"
    outside = tmp_path / "External"
    datadir.mkdir()
    outside.mkdir()
    root = datadir / "root.par"
    external = outside / "external.par"
    leaf = outside / "leaf.par"
    root.write_text(
        f"#FullDataName Root\nPARSFILE {external}\nEND\n", encoding="utf-8"
    )
    external.write_text(
        f"#FullDataName External\nPARSFILE {leaf}\nEND\n", encoding="utf-8"
    )
    leaf.write_text("#FullDataName Leaf\nEND\n", encoding="utf-8")
    return datadir, root, external, leaf


def test_external_dependency_recorded_but_not_followed(external_graph):
    datadir, root, external, leaf = external_graph
    graph = database.build_dependency_graph(root, datadir)
    assert graph.issues_by_code("external_reference")
    assert graph.nodes[str(external.resolve())].external
    assert str(leaf.resolve()) not in graph.nodes


def test_external_dependency_opt_in_and_legacy_containment(external_graph):
    datadir, root, external, leaf = external_graph
    graph = database.build_dependency_graph(root, datadir, allow_external=True)
    assert graph.nodes[str(external.resolve())].external
    assert graph.nodes[str(leaf.resolve())].external
    legacy = database.resolve_dataset_tree(root, datadir)
    assert legacy["links"][0]["external"] is True
    assert legacy["links"][0]["links"] == []
    followed = database.resolve_dataset_tree(root, datadir, allow_external=True)
    assert followed["links"][0]["links"][0]["external"] is True


def test_override_capability_levels_and_dynamic_echo_policy():
    assert ScalarOverride("M_SU", 1).echo_validation == "required"
    assert ScalarOverride("UNKNOWN_SCALAR", 1).echo_validation == "best_effort"
    assert ScalarOverride("M_SU", 1).capability.verification is VerificationLevel.CARSIM_TESTED
    assert (
        ScalarOverride("UNKNOWN_SCALAR", 1).capability.verification
        is VerificationLevel.CONTEXT_REQUIRED
    )
    assert (
        TableOverride("SPEED_TARGET_TABLE", [(0, 1), (1, 2)]).capability.verification
        is VerificationLevel.CARSIM_TESTED
    )
    assert (
        TableOverride("UNKNOWN_TABLE", [(0, 1), (1, 2)]).capability.verification
        is VerificationLevel.CONTEXT_REQUIRED
    )
    assert (
        ReferenceOverride("PARSFILE", "Known dataset").capability.verification
        is VerificationLevel.CONTEXT_REQUIRED
    )
    reference = ReferenceOverride("PARSFILE", "Known dataset")
    assert reference.resolution_verification is VerificationLevel.UNIT_TESTED
    assert reference.compatibility_verification is VerificationLevel.CONTEXT_REQUIRED


def _synthetic_run(tmp_path, echo_text):
    pd.DataFrame({"Time": [0.0, 0.1], "Vx": [0.0, 0.0]}).to_csv(
        tmp_path / "run.csv", index=False
    )
    (tmp_path / "run_echo.par").write_text(echo_text, encoding="utf-8")
    (tmp_path / "run_log.txt").write_text("synthetic", encoding="utf-8")


def test_echo_policy_required_best_effort_and_none(tmp_path):
    _synthetic_run(tmp_path, "OTHER 1\n")
    required = check_run(
        tmp_path,
        SimulationConfig(0.1, 0.1),
        ["Vx"],
        expected_parameters={"M_SU": {"value": 1, "echo_validation": "required"}},
    )
    assert not required.passed and required.errors()[0].code == "echo_absent"
    best = check_run(
        tmp_path,
        SimulationConfig(0.1, 0.1),
        ["Vx"],
        expected_parameters={
            "UNKNOWN_SCALAR": {"value": 1, "echo_validation": "best_effort"}
        },
    )
    assert best.passed and best.warnings()[0].code == "echo_absent"
    none = check_run(
        tmp_path,
        SimulationConfig(0.1, 0.1),
        ["Vx"],
        expected_parameters={"UNKNOWN_SCALAR": {"value": 1, "echo_validation": "none"}},
    )
    assert none.passed and not none.warnings()


def test_best_effort_mismatch_is_error(tmp_path):
    _synthetic_run(tmp_path, "UNKNOWN_SCALAR 2\n")
    report = check_run(
        tmp_path,
        SimulationConfig(0.1, 0.1),
        ["Vx"],
        expected_parameters={
            "UNKNOWN_SCALAR": {"value": 1, "echo_validation": "best_effort"}
        },
    )
    assert not report.passed and report.errors()[0].code == "echo_mismatch"
