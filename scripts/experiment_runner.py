"""Compile/run a pinned research experiment and persist a reproducibility manifest."""
import argparse
import copy
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import shutil
import subprocess
import time

from carsim_batch import make_scenario, resolve_paths, run_solver
from result_contract import load_run
from scenario_schema import SimulationConfig, VehicleOverrides, load_experiment, validate_experiment
from sensor_replay import replay
from validate_run import validate_run
from vehicle_registry import resolve_vehicle, sha256


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def provenance():
    root = Path(__file__).resolve().parents[1]
    versions = {}
    for package in ("pandas", "numpy", "PyYAML", "jsonschema", "torch"):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = None
    git = {}
    for key, args in (("commit", ["rev-parse", "HEAD"]), ("status", ["status", "--porcelain", "--untracked-files=normal"])):
        try:
            proc = subprocess.run(["git"] + args, cwd=root, capture_output=True, text=True, timeout=10)
            git[key] = proc.stdout.strip() if proc.returncode == 0 else None
        except (OSError, subprocess.TimeoutExpired):
            git[key] = None
    # Hash sources as well: commit alone cannot describe an uncommitted checkout.
    hashes = {str(p.relative_to(root)): sha256(p) for folder, pattern in
              (("scripts", "*.py"), ("schemas", "*.json"), ("tests", "*.py"),
               ("examples", "*.yaml")) for p in (root / folder).glob(pattern)}
    return {"python": platform.python_version(), "platform": platform.platform(),
            "packages": versions, "git": git, "source_sha256": hashes}


def expand_experiments(config):
    variants = config.get("sweep")
    if variants is None:
        return [config]
    result = []
    ids = set()
    for variant in variants:
        item = copy.deepcopy(config)
        item.pop("sweep")
        item["experiment"]["id"] += "_" + variant["id"]
        if item["experiment"]["id"] in ids:
            raise ValueError("Duplicate sweep id")
        ids.add(item["experiment"]["id"])
        for section in ("road", "vehicle_parameters"):
            if section in variant:
                item.setdefault(section, {}).update(variant[section])
        result.append(validate_experiment(item))
    return result


def run_experiment(config, registry, output_root, prog=None, datadir=None,
                   execute=False, timeout=600):
    validate_experiment(config)
    if "sweep" in config:
        raise ValueError("Expand sweep before calling run_experiment")
    prog, datadir, _ = resolve_paths(prog, datadir, require=("prog", "datadir"))
    runtime = {"prog": Path(prog), "datadir": Path(datadir),
               "cli": Path(prog) / "Programs" / "VS_SolverWrapper_CLI_64.exe",
               "dll": Path(prog) / "Programs" / "solvers" / "carsim_64.dll"}
    for key, path in runtime.items():
        if not (path.is_dir() if key in ("prog", "datadir") else path.is_file()):
            raise ValueError("Invalid runtime %s: %s" % (key, path))
    vehicle = resolve_vehicle(registry, config["vehicle"]["base"], prog)
    directory = Path(output_root).resolve() / config["experiment"]["id"]
    directory.mkdir(parents=True, exist_ok=False)  # refuse reuse, including dry runs
    manifest = {"manifest_version": 1, "created_utc": utc_now(), "status": "preparing",
                "config": config, "vehicle": vehicle, "provenance": provenance(),
                "runtime": {k: str(v.resolve()) for k, v in runtime.items()},
                "runtime_sha256": {k: sha256(runtime[k]) for k in ("cli", "dll")}}
    manifest_path = directory / "manifest.json"

    def save():
        manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n", encoding="utf-8")

    try:
        save()
        base_copy = directory / "base_Run_all.par"
        shutil.copyfile(vehicle["base_run_all"], base_copy)
        if sha256(base_copy) != vehicle["base_sha256"]:
            raise ValueError("Base changed during snapshot")
        simulation = SimulationConfig(**config["simulation"])
        overrides = VehicleOverrides(**config.get("vehicle_parameters", {}))
        outputs = list(dict.fromkeys(config["outputs"]["estimator"] + config["outputs"]["evaluator"]))
        if config.get("validation", {}).get("minimum_speed_mps") and "Vx" not in outputs:
            outputs.append("Vx")
        outputs = [n for n in outputs if n != "Time"]
        sim = make_scenario(str(directory), str(base_copy), prog, datadir,
                            config=simulation, speed_rows=config["maneuver"]["speed_kmh"],
                            steer_rows=config["maneuver"]["steering_deg"], mu=config["road"]["mu"],
                            vehicle_overrides=overrides, outputs=outputs,
                            product_version=vehicle["carsim_version"])
        manifest["status"] = "compiled"
        manifest["input_sha256"] = {n: sha256(directory / n) for n in ("override.par", "simfile.sim", "base_Run_all.par")}
        save()
        if not execute:
            return directory
        manifest["status"] = "running"
        manifest["started_utc"] = utc_now()
        save()
        started = time.time()
        stdout = run_solver(sim, prog, timeout)
        (directory / "solver_stdout.txt").write_text(stdout, encoding="utf-8")
        manifest["validation"] = validate_run(
            directory, simulation, outputs, started,
            {**overrides.keywords(), "TSTEP": simulation.dt, "TSTOP": simulation.duration, "IPRINT": 1},
            **config.get("validation", {}))
        run = load_run(directory / "run.csv", config["outputs"]["estimator"])
        run.estimator_view().to_csv(directory / "observable.csv", index=False)
        run.truth.to_csv(directory / "truth.csv", index=False)
        manifest["channels"] = run.metadata
        if config.get("sensors"):
            packets = replay(run.estimator_view(), config["sensors"], config["experiment"]["seed"])
            for name, frame in packets.items():
                frame.to_csv(directory / ("sensor_" + name + ".csv"), index=False)
            manifest["sensor_packets"] = {name: len(frame) for name, frame in packets.items()}
        manifest["output_sha256"] = {p.name: sha256(p) for p in directory.iterdir()
                                      if p.is_file() and p.name not in {"manifest.json", *manifest["input_sha256"]}}
        manifest["status"] = "passed"
        return directory
    except Exception as exc:
        manifest["status"] = "failed"
        manifest["error"] = "%s: %s" % (type(exc).__name__, exc)
        raise
    finally:
        manifest["finished_utc"] = utc_now()
        save()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenario")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--prog")
    parser.add_argument("--datadir")
    parser.add_argument("--run", action="store_true", help="Execute solver; default only compiles")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    configs = expand_experiments(load_experiment(args.scenario))
    for config in configs:
        print(run_experiment(config, args.registry, args.out, args.prog, args.datadir, args.run, args.timeout))


if __name__ == "__main__":
    main()
