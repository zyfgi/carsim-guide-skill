"""Explicit vehicle bindings; no newest-file fallback. Registry paths are local."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def product_version(prog, explicit=None):
    match = re.search(r"CarSim[ _-]?(\d{4}\.\d+)", str(prog), re.I)
    discovered = match.group(1) if match else None
    if explicit is not None and not re.fullmatch(r"\d{4}\.\d+", explicit):
        raise ValueError("CarSim version must look like 2024.0")
    if explicit and discovered and explicit != discovered:
        raise ValueError("Pinned CarSim version disagrees with install directory")
    if not (explicit or discovered):
        raise ValueError("Cannot infer CarSim version; supply product_version explicitly")
    return explicit or discovered


def bind_vehicle(registry_path, name, base, version, run_control, powertrain):
    path = Path(registry_path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"vehicles": {}}
    if name in data["vehicles"]:
        raise ValueError("Vehicle already bound; use a new name for a new base revision")
    base = Path(base).resolve(strict=True)
    product_version("", version)
    data["vehicles"][name] = {"base_run_all": str(base), "base_sha256": sha256(base),
                               "carsim_version": version, "run_control": run_control,
                               "powertrain": powertrain}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def resolve_vehicle(registry_path, name, prog):
    data = json.loads(Path(registry_path).read_text(encoding="utf-8"))
    entry = dict(data["vehicles"][name])
    base = Path(entry["base_run_all"])
    if not base.is_absolute():
        base = Path(registry_path).resolve().parent / base
    if sha256(base) != entry["base_sha256"]:
        raise ValueError("Base SHA256 mismatch for vehicle %s" % name)
    product_version(prog, entry["carsim_version"])
    entry["base_run_all"] = str(base.resolve())
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("registry", "name", "base", "version", "run-control", "powertrain"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args()
    bind_vehicle(args.registry, args.name, args.base, args.version, args.run_control, args.powertrain)


if __name__ == "__main__":
    main()
