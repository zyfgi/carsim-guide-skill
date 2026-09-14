"""Deprecated location: explicit base bindings live in base_registry.py.

This wrapper keeps the old vehicle-registry API working. Existing registry
files with a legacy top-level "vehicles" section keep resolving; new bindings
are written in the "bases" shape.
"""
import argparse

from base_registry import bind_base, product_version, resolve_base, sha256  # noqa: F401


def bind_vehicle(registry_path, name, base, version, run_control, powertrain):
    """Deprecated: use base_registry.bind_base(..., vehicle=powertrain)."""
    bind_base(registry_path, name, base, version,
              run_control=run_control, vehicle=powertrain)


def resolve_vehicle(registry_path, name, prog=None):
    """Deprecated: use base_registry.resolve_base(). Returns the base record;
    the legacy "powertrain" field name is mirrored from "vehicle" when present."""
    entry = resolve_base(registry_path, name, prog)
    if "powertrain" not in entry and "vehicle" in entry:
        entry["powertrain"] = entry["vehicle"]
    return entry


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for flag in ("registry", "name", "base", "version", "run-control", "powertrain"):
        parser.add_argument("--" + flag, required=True)
    args = parser.parse_args()
    bind_vehicle(args.registry, args.name, args.base, args.version,
                 args.run_control, args.powertrain)


if __name__ == "__main__":
    main()
