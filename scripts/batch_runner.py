"""Cartesian/zip scenario sweeps built strictly on scenario_runner."""
import argparse
import itertools
import json
from collections.abc import Iterable
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

import yaml
from scenario_runner import MANIFEST_NAME, run_scenario
from scenario_schema import load_scenario, validate_scenario

BATCH_MANIFEST_NAME = "batch_manifest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def expand_sweep(sweep: dict[str, dict], mode: str = "cartesian") -> list[dict[str, object]]:
    """Expand non-empty ``values`` entries using cartesian or zip semantics."""
    if mode not in {"cartesian", "zip"}:
        raise ValueError("combination must be 'cartesian' or 'zip'")
    if not sweep:
        raise ValueError("sweep must not be empty")
    names = list(sweep)
    values = []
    for name in names:
        spec = sweep[name]
        if set(spec) != {"values"} or not isinstance(spec["values"], list) or not spec["values"]:
            raise ValueError(f"Sweep {name} must contain one non-empty values list")
        values.append(spec["values"])
    if mode == "zip":
        lengths = {len(item) for item in values}
        if len(lengths) != 1:
            raise ValueError("zip sweeps require equal values lengths")
        rows: Iterable[tuple[object, ...]] = zip(*values)
    else:
        rows = itertools.product(*values)
    return [dict(zip(names, row)) for row in rows]


def apply_combination(base: dict, combination: dict[str, object]) -> dict:
    """Apply supported dotted sweep targets to a copied scenario."""
    scenario = deepcopy(base)
    for dotted, value in combination.items():
        parts = dotted.split(".")
        if len(parts) == 2 and parts[0] == "parameters":
            keyword = parts[1]
            parameters = scenario.setdefault("parameters", [])
            matches = [item for item in parameters
                       if item.get("type", "scalar") == "scalar" and
                       item.get("keyword") == keyword]
            if len(matches) > 1:
                raise ValueError(f"Scenario has duplicate scalar parameter {keyword}")
            if matches:
                matches[0]["value"] = value
            else:
                parameters.append({"keyword": keyword, "value": value})
            continue
        target = scenario
        for part in parts[:-1]:
            if part not in target or not isinstance(target[part], dict):
                raise ValueError(f"Unknown sweep target: {dotted}")
            target = target[part]
        if parts[-1] not in target:
            raise ValueError(f"Unknown sweep target: {dotted}")
        target[parts[-1]] = value
    return validate_scenario(scenario)


def load_batch(path: str | Path) -> tuple[dict, dict, Path]:
    """Load a batch YAML and its relative base scenario."""
    batch_path = Path(path).resolve()
    config = yaml.safe_load(batch_path.read_text(encoding="utf-8"))
    allowed = {"batch", "base_scenario", "sweep", "combination"}
    if not isinstance(config, dict) or set(config) - allowed:
        raise ValueError("Batch config has unknown fields")
    if not isinstance(config.get("batch"), dict) or set(config["batch"]) != {"id"}:
        raise ValueError("batch must contain exactly id")
    base_path = (batch_path.parent / config["base_scenario"]).resolve()
    return config, load_scenario(base_path), base_path


def run_batch(batch: str | Path, registry: str | Path,
              output_root: str | Path, prog: str | None = None,
              datadir: str | None = None, execute: bool = False,
              fail_fast: bool = False, timeout: float = 600) -> Path:
    """Compile/run isolated variants and always maintain a batch manifest."""
    config, base, base_path = load_batch(batch)
    batch_id = config["batch"]["id"]
    if not isinstance(batch_id, str) or not batch_id or any(c not in
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in batch_id):
        raise ValueError("Invalid batch id")
    combinations = expand_sweep(config["sweep"], config.get("combination", "cartesian"))
    root = Path(output_root).resolve() / batch_id
    if root.exists():
        raise FileExistsError(f"Batch directory already exists: {root}")
    root.mkdir(parents=True)
    manifest_path = root / BATCH_MANIFEST_NAME
    manifest = {
        "manifest_version": 1,
        "batch": {"id": batch_id, "created_utc": _utc_now(),
                  "finished_utc": None, "combination": config.get("combination", "cartesian")},
        "base_scenario": str(base_path),
        "sweep": config["sweep"],
        "runs": [],
    }

    def save() -> None:
        manifest_path.write_text(json.dumps(manifest, indent=2, allow_nan=False) + "\n",
                                 encoding="utf-8")

    save()
    try:
        for index, combination in enumerate(combinations, 1):
            run_id = f"run_{index:04d}"
            scenario = apply_combination(base, combination)
            scenario["scenario"]["id"] = run_id
            record = {"run_id": run_id, "parameters": combination,
                      "status": "preparing", "success": False,
                      "manifest_path": str(root / run_id / MANIFEST_NAME)}
            manifest["runs"].append(record)
            save()
            try:
                run_scenario(scenario, registry, root, prog, datadir,
                             execute=execute, timeout=timeout)
                run_manifest = json.loads(Path(record["manifest_path"]).read_text(encoding="utf-8"))
                record["status"] = run_manifest["run"]["status"]
                record["success"] = record["status"] in {"compiled", "passed"}
            except Exception as exc:
                record["status"] = "failed"
                record["error"] = f"{type(exc).__name__}: {exc}"
                save()
                if fail_fast:
                    raise
            save()
    finally:
        manifest["batch"]["finished_utc"] = _utc_now()
        manifest["summary"] = {
            "total": len(manifest["runs"]),
            "successful": sum(bool(item["success"]) for item in manifest["runs"]),
            "failed": sum(item["status"] == "failed" for item in manifest["runs"]),
        }
        save()
    return root


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch")
    parser.add_argument("--registry", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--prog")
    parser.add_argument("--datadir")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--fail-fast", action="store_true")
    parser.add_argument("--timeout", type=float, default=600)
    args = parser.parse_args()
    print(run_batch(args.batch, args.registry, args.out, args.prog, args.datadir,
                    args.run, args.fail_fast, args.timeout))


if __name__ == "__main__":
    main()
