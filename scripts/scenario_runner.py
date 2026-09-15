"""Generic scenario runner: YAML in -> compiled scenario -> (solver) ->
validated run + run_manifest.json.

This is the high-level entry point for ordinary CarSim scenarios. It delegates
all solver mechanics to carsim_batch (never re-implements them), resolves the
base by explicit name + SHA256 via base_registry, and validates results with
validate_run.check_run. The manifest records only generic run facts - no
research/estimator/sensor fields; research layers extend it.

    python scripts/scenario_runner.py scenario.yaml --registry bases.local.json \
        --out runs --run
"""
import argparse
import json
import platform
import re
import shutil
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import carsim_batch as cb
from base_registry import resolve_base, sha256
from parameters import ScalarOverride, coerce_structured_overrides
from scenario_schema import SimulationConfig, VehicleOverrides, load_scenario, validate_scenario
from validate_run import ValidationIssue, check_run
from version_compatibility import compatibility_status

MANIFEST_NAME = "run_manifest.json"


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def _git_commit():
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], timeout=10,
                              capture_output=True, text=True,
                              cwd=Path(__file__).resolve().parents[1])
        return proc.stdout.strip() if proc.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def compile_scenario(config, base_entry, prog, datadir, directory):
    """Snapshot the base and write override.par + simfile.sim into <directory>.

    Delegates generation to carsim_batch.make_scenario (single source of the
    override.par pattern). Returns compile info consumed by run/verify steps.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)  # exclusivity enforced by run_scenario
    base_copy = directory / "base_Run_all.par"
    shutil.copyfile(base_entry["base_run_all"], base_copy)
    if sha256(base_copy) != base_entry["base_sha256"]:
        raise ValueError("Base changed during snapshot")
    simulation = SimulationConfig(**config["simulation"])
    vehicle = VehicleOverrides(**config.get("vehicle", {}))
    overrides = coerce_structured_overrides(config.get("parameters", []))
    scalar = [item for item in overrides if isinstance(item, ScalarOverride)]
    structured = [item for item in overrides if not isinstance(item, ScalarOverride)]
    outputs = [n for n in config["outputs"]["channels"] if n != "Time"]
    if config.get("validation", {}).get("minimum_speed_mps") and "Vx" not in outputs:
        outputs.append("Vx")
    simfile = cb.make_scenario(
        str(directory), str(base_copy), prog, datadir, config=simulation,
        speed_rows=config["maneuver"]["speed_kmh"],
        steer_rows=config["maneuver"]["steering_deg"], mu=config["road"]["friction"],
        vehicle_overrides=vehicle, scalar_overrides=scalar,
        structured_overrides=structured, outputs=outputs,
        product_version=base_entry["carsim_version"])
    expected = dict(vehicle.keywords())
    for override in scalar:
        expected[override.keyword] = {"value": override.value,
                                      "echo_validation": override.echo_validation}
    expected.update({"TSTEP": simulation.dt, "TSTOP": simulation.duration, "IPRINT": 1})
    capabilities = []
    for override in overrides:
        capability = override.capability
        capabilities.append({
            "kind": capability.kind,
            "keyword": capability.keyword or getattr(override, "keyword", None),
            "dataset_family": capability.dataset_family,
            "verification": capability.verification.value,
            "evidence": capability.evidence,
        })
    return {"directory": directory, "simfile": simfile, "simulation": simulation,
            "outputs": outputs, "expected_parameters": expected,
            "base_copy": base_copy, "override_capabilities": capabilities}


def verify_compiled(directory, info, base_entry):
    """Compile-time checks on the generated files (before any solver call)."""
    issues = []
    add = lambda code, msg: issues.append(ValidationIssue("error", code, msg))
    par_text = (Path(directory) / "override.par").read_text(encoding="utf-8", errors="replace")
    sim_text = Path(info["simfile"]).read_text(encoding="utf-8", errors="replace")
    tstep_par = re.search(r"^TSTEP\s+([^\s]+)", par_text, re.M)
    tstep_sim = re.search(r"^EXT_MODEL_STEP\s+([^\s]+)", sim_text, re.M)
    if not tstep_par or not tstep_sim or float(tstep_par.group(1)) != float(tstep_sim.group(1)):
        add("dt_mismatch", "TSTEP (override.par) must equal EXT_MODEL_STEP (simfile.sim)")
    dll = re.search(r"^DLLFILE\s+(.+)$", sim_text, re.M)
    if not dll or "carsim_64" not in dll.group(1).lower():
        add("dll_not_64bit", "DLLFILE must pin the 64-bit solver (carsim_64.dll)")
    version = re.search(r"^PRODUCT_VER\s+([^\s]+)", sim_text, re.M)
    if not version or version.group(1) != base_entry["carsim_version"]:
        add("version_unresolved", "PRODUCT_VER missing or disagrees with the pinned base version")
    if not re.search(r"^WRT_", par_text, re.M):
        add("empty_outputs", "override.par declares no WRT_ output channels")
    if sha256(info["base_copy"]) != base_entry["base_sha256"]:
        add("base_changed", "Base snapshot hash no longer matches the registry binding")
    return issues


def _artifacts(directory):
    names = {"override_par": "override.par", "simfile": "simfile.sim",
             "run_csv": "run.csv", "run_echo": "run_echo.par",
             "run_log": "run_log.txt", "solver_stdout": "solver_stdout.txt",
             "base_run_all": "base_Run_all.par", "scenario": "scenario.yaml"}
    return {key: str(directory / name) for key, name in names.items()
            if (directory / name).is_file()}


def run_scenario(scenario, registry, output_root, prog=None, datadir=None,
                 execute=False, timeout=600):
    """Compile (and optionally run + validate) one generic scenario.

    <scenario> is a path to YAML/JSON or an already-validated config dict.
    Returns the scenario directory; the manifest lives next to it as
    run_manifest.json.
    """
    if isinstance(scenario, (str, Path)):
        config = load_scenario(scenario)
    else:
        config = validate_scenario(scenario)
    prog, datadir, _ = cb.resolve_paths(prog, datadir, require=("prog", "datadir"))
    base_entry = resolve_base(registry, config["base"]["name"], prog)
    directory = Path(output_root).resolve() / config["scenario"]["id"]
    if directory.exists():
        raise FileExistsError("Scenario directory already exists: %s" % directory)
    directory.mkdir(parents=True)
    import yaml
    (directory / "scenario.yaml").write_text(
        yaml.safe_dump(config, sort_keys=False, allow_unicode=True), encoding="utf-8")

    cli = Path(prog) / "Programs" / "VS_SolverWrapper_CLI_64.exe"
    dll = Path(prog) / "Programs" / "solvers" / "carsim_64.dll"
    version_status = compatibility_status(base_entry["carsim_version"])
    manifest = {
        "manifest_version": 1,
        "run": {"id": config["scenario"]["id"], "created_utc": utc_now(),
                "started_utc": None, "finished_utc": None, "status": "preparing"},
        "carsim": {"version": base_entry["carsim_version"],
                   "version_verified": version_status.verified,
                   "compatibility_warning": version_status.warning,
                   "verified_features": sorted(version_status.features), "prog": str(prog),
                   "datadir": str(datadir), "solver": str(cli), "dll": str(dll),
                   "solver_sha256": sha256(cli), "dll_sha256": sha256(dll)},
        "base": {"name": base_entry["name"],
                 "base_run_all": base_entry["base_run_all"],
                 "sha256": base_entry["base_sha256"]},
        "scenario": config,
        "artifacts": {}, "input_sha256": {}, "output_sha256": {},
        "validation": None,
        "provenance": {"python": platform.python_version(),
                       "platform": platform.platform(),
                       "git_commit": _git_commit()},
    }
    manifest_path = directory / MANIFEST_NAME

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n",
                                 encoding="utf-8")

    try:
        save()
        info = compile_scenario(config, base_entry, prog, datadir, directory)
        manifest["override_capabilities"] = info["override_capabilities"]
        issues = verify_compiled(directory, info, base_entry)
        if issues:
            raise ValueError("Compile check failed: %s" % "; ".join(
                "%s: %s" % (i.code, i.message) for i in issues))
        manifest["input_sha256"] = {n: sha256(directory / n)
                                    for n in ("scenario.yaml", "override.par", "simfile.sim",
                                              "base_Run_all.par")}
        manifest["run"]["status"] = "compiled"
        save()
        if not execute:
            return directory
        manifest["run"]["status"] = "running"
        manifest["run"]["started_utc"] = utc_now()
        save()
        started = time.time()
        stdout = cb.run_solver(info["simfile"], prog, timeout)
        (directory / "solver_stdout.txt").write_text(stdout, encoding="utf-8")
        validation = check_run(directory, info["simulation"], info["outputs"],
                               started, info["expected_parameters"],
                               **(config.get("validation") or {}),
                               solver_stdout=stdout)
        manifest["validation"] = {"passed": validation.passed,
                                  "issues": [asdict(i) for i in validation.issues],
                                  "metrics": validation.metrics}
        if not validation.passed:
            first = validation.errors()[0]
            raise ValueError("%s: %s" % (first.code, first.message))
        manifest["output_sha256"] = {p.name: sha256(p) for p in directory.iterdir()
                                     if p.is_file() and p.name not in
                                     {MANIFEST_NAME, *manifest["input_sha256"]}}
        manifest["run"]["status"] = "passed"
        return directory
    except Exception as exc:
        manifest["run"]["status"] = "failed"
        manifest["error"] = "%s: %s" % (type(exc).__name__, exc)
        raise
    finally:
        manifest["run"]["finished_utc"] = utc_now()
        manifest["artifacts"] = _artifacts(directory)
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario", help="scenario YAML/JSON path")
    parser.add_argument("--registry", required=True, help="base registry JSON")
    parser.add_argument("--out", required=True, help="output root directory")
    parser.add_argument("--prog")
    parser.add_argument("--datadir")
    parser.add_argument("--run", action="store_true", help="execute the solver; default compiles only")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    print(run_scenario(args.scenario, args.registry, args.out,
                       args.prog, args.datadir, args.run, args.timeout))


if __name__ == "__main__":
    main()
