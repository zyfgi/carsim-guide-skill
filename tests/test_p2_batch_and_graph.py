"""P2 batch isolation and dataset dependency graph tests."""
import json
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import batch_runner as batch
import database_tools as database


def test_batch_cartesian():
    rows = batch.expand_sweep({"a": {"values": [1, 2]}, "b": {"values": [3, 4]}})
    assert rows == [{"a": 1, "b": 3}, {"a": 1, "b": 4},
                    {"a": 2, "b": 3}, {"a": 2, "b": 4}]


def test_batch_zip():
    rows = batch.expand_sweep({"a": {"values": [1, 2]}, "b": {"values": [3, 4]}}, "zip")
    assert rows == [{"a": 1, "b": 3}, {"a": 2, "b": 4}]
    with pytest.raises(ValueError, match="equal"):
        batch.expand_sweep({"a": {"values": [1]}, "b": {"values": [2, 3]}}, "zip")


@pytest.fixture()
def batch_files(tmp_path):
    scenario = {
        "schema_version": 1, "scenario": {"id": "base"}, "base": {"name": "sedan"},
        "simulation": {"duration": 1.0, "dt": 0.1}, "road": {"friction": 0.8},
        "maneuver": {"speed_kmh": [[0, 10], [1, 10]],
                     "steering_deg": [[0, 0], [1, 0]]},
        "outputs": {"channels": ["Vx"]},
    }
    (tmp_path / "scenario.yaml").write_text(yaml.safe_dump(scenario), encoding="utf-8")
    spec = {"batch": {"id": "grid"}, "base_scenario": "scenario.yaml",
            "sweep": {"road.friction": {"values": [0.4, 0.8, 1.0]}}}
    path = tmp_path / "batch.yaml"
    path.write_text(yaml.safe_dump(spec), encoding="utf-8")
    return path


@pytest.fixture()
def batch_result(batch_files, tmp_path, monkeypatch):
    calls = []

    def fake_run(scenario, registry, output_root, *args, **kwargs):
        run_dir = Path(output_root) / scenario["scenario"]["id"]
        run_dir.mkdir()
        (run_dir / "scenario.yaml").write_text(yaml.safe_dump(scenario), encoding="utf-8")
        status = "failed" if scenario["road"]["friction"] == 0.8 else "compiled"
        (run_dir / "run_manifest.json").write_text(
            json.dumps({"run": {"status": status}}), encoding="utf-8")
        calls.append(run_dir)
        if status == "failed":
            raise RuntimeError("synthetic failure")
        return run_dir

    monkeypatch.setattr(batch, "run_scenario", fake_run)
    root = batch.run_batch(batch_files, "registry.json", tmp_path / "runs")
    manifest = json.loads((root / "batch_manifest.json").read_text(encoding="utf-8"))
    return calls, manifest


def test_batch_independent_run_dirs(batch_result):
    calls, _ = batch_result
    assert [path.name for path in calls] == ["run_0001", "run_0002", "run_0003"]
    assert all((path / "scenario.yaml").is_file() for path in calls)


def test_batch_failure_isolation(batch_result):
    calls, manifest = batch_result
    assert len(calls) == 3
    assert manifest["runs"][1]["status"] == "failed"


def test_batch_manifest(batch_result):
    _, manifest = batch_result
    assert manifest["summary"] == {"total": 3, "successful": 2, "failed": 1}


@pytest.fixture()
def graph_files(tmp_path):
    files = {name: tmp_path / f"{name}.par" for name in "abcd"}
    files["a"].write_text("#FullDataName Vehicle\nPARSFILE b.par\nPARSFILE c.par\nEND\n")
    files["b"].write_text("#FullDataName Suspension\nPARSFILE d.par\nEND\n")
    files["c"].write_text("#FullDataName Steering\nPARSFILE d.par\nPARSFILE missing.par\nEND\n")
    files["d"].write_text("#FullDataName Spring\nPARSFILE a.par\nEND\n")
    return tmp_path, files


def test_dependency_graph(graph_files):
    root, files = graph_files
    graph = database.build_dependency_graph(files["a"], root)
    assert len(graph.nodes) == 5
    assert graph.nodes[str(files["a"].resolve())].full_data_name == "Vehicle"
    assert "Vehicle" in database.format_dependency_tree(graph)


def test_dependency_cycle(graph_files):
    root, files = graph_files
    graph = database.build_dependency_graph(files["a"], root)
    assert graph.issues_by_code("cycle")


def test_missing_dependency(graph_files):
    root, files = graph_files
    graph = database.build_dependency_graph(files["a"], root)
    assert graph.issues_by_code("missing_reference")


def test_duplicate_dependency(graph_files):
    root, files = graph_files
    graph = database.build_dependency_graph(files["a"], root)
    assert graph.issues_by_code("duplicate_dataset")


def test_graph_depth_limit(graph_files):
    root, files = graph_files
    graph = database.build_dependency_graph(files["a"], root, max_depth=0)
    assert graph.issues_by_code("depth_limit") and len(graph.nodes) == 1


def test_database_roots_cannot_escape_datadir(tmp_path):
    datadir = tmp_path / "data"
    outside = tmp_path / "outside"
    datadir.mkdir()
    outside.mkdir()
    with pytest.raises(ValueError, match="inside DATADIR"):
        database.find_datasets(datadir, "x", roots=[outside])
