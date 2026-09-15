"""Explicit GUI-expanded base bindings: name + SHA256, never newest-file.

A bound "base" is a GUI-expanded Run_all.par. It fixes more than the vehicle:
typically vehicle + procedure + controls + road context. Bindings live in a
machine-local JSON registry (never committed). Resolving re-verifies the
SHA256 and the CarSim version on every use; a changed base fails loudly
instead of silently switching vehicles.

Registry files may still contain a legacy top-level "vehicles" section (see
older registry formats); both shapes resolve.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

from carsim_errors import BaseResolutionError, VersionCompatibilityError
from version_compatibility import parse_version

_REQUIRED = ("base_run_all", "base_sha256", "carsim_version")


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
        raise VersionCompatibilityError("CarSim version must look like 2024.0")
    if explicit and discovered and explicit != discovered:
        raise VersionCompatibilityError("Pinned CarSim version disagrees with install directory")
    if not (explicit or discovered):
        raise VersionCompatibilityError(
            "Cannot infer CarSim version; supply carsim_version explicitly")
    value = explicit or discovered
    parse_version(value)
    return value


def _load(registry_path):
    path = Path(registry_path)
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    bases = data.get("bases")
    if bases is None:
        bases = data.get("vehicles", {})  # legacy vehicle-registry shape
    return path, data, bases


def bind_base(registry_path, name, base_run_all, carsim_version,
              run_control=None, vehicle=None, procedure=None, notes=None):
    """Bind <name> to one exact base file; refuses to overwrite a name."""
    path, data, bases = _load(registry_path)
    if name in bases or name in data.get("vehicles", {}):
        raise ValueError("Base name already bound; use a new name for a new base revision")
    base = Path(base_run_all).resolve(strict=True)
    product_version("", carsim_version)
    record = {"base_run_all": str(base), "base_sha256": sha256(base),
              "carsim_version": carsim_version}
    for key, value in (("run_control", run_control), ("vehicle", vehicle),
                       ("procedure", procedure), ("notes", notes)):
        if value:
            record[key] = value
    data.setdefault("bases", {})[name] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return record


def resolve_base(registry_path, name, prog=None):
    """Resolve a bound base by name; re-verifies SHA256 and version."""
    _, _, bases = _load(registry_path)
    try:
        entry = dict(bases[name])
    except KeyError:
        raise BaseResolutionError(
            "Unknown base name %r; bind it explicitly first "
            "(python scripts/base_registry.py --registry ... --bind)" % name) from None
    missing = [key for key in _REQUIRED if key not in entry]
    if missing:
        raise BaseResolutionError("Base record %s is missing fields: %s" % (name, missing))
    base = Path(entry["base_run_all"])
    if not base.is_absolute():
        base = Path(registry_path).resolve().parent / base
    if sha256(base) != entry["base_sha256"]:
        raise BaseResolutionError("Base SHA256 mismatch for %s; bind a new name to "
                         "deliberately adopt the new revision" % name)
    product_version(prog, entry["carsim_version"])
    entry["base_run_all"] = str(base.resolve())
    entry["name"] = name
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--base", required=True, help="absolute Run_all.par path")
    parser.add_argument("--version", required=True, help="e.g. 2024.0")
    parser.add_argument("--run-control")
    parser.add_argument("--vehicle")
    parser.add_argument("--procedure")
    parser.add_argument("--notes")
    args = parser.parse_args()
    bind_base(args.registry, args.name, args.base, args.version,
              run_control=args.run_control, vehicle=args.vehicle,
              procedure=args.procedure, notes=args.notes)


if __name__ == "__main__":
    main()
