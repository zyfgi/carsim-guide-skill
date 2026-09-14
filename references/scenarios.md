# Generic scenarios (YAML → compile → run → manifest)

A generic scenario describes one ordinary CarSim run: base, timing, road
friction, maneuver profiles, vehicle parameters, extra scalar overrides and
requested output channels. No research concepts exist at this layer — every
registered channel (tire forces included) is a legal output; estimator
isolation lives in the optional workflow layer only.

## Define

Start from an example in `examples/scenarios/` (bind the base name first —
see below). Full contract: `schemas/scenario.schema.json`.

```yaml
schema_version: 1
scenario:
  id: double_lane_change_mu08     # also the output directory name
base:
  name: distributed_ev            # resolved via the base registry, never "newest"
simulation:
  dt: 0.001                       # default 0.001 s; any value with integral steps
  duration: 30.0                  # seconds
road:
  friction: 0.8                   # uniform MU_ROAD_CARPET override
maneuver:
  speed_kmh:    [[0.0, 50.0], [30.0, 50.0]]        # closed-loop target table
  steering_deg: [[0.0, 0.0], [5.0, 20.0], [6.0, -20.0], [30.0, 0.0]]  # open-loop SW angle
vehicle:                          # typed VehicleOverrides fields (SI)
  sprung_mass_kg: 1250.0
parameters: []                    # ScalarOverride list: [{keyword: M_SU, value: 1250.0}]
outputs:
  channels: [Vx, Vy, AVz, Fx_L1, Fy_L1]   # exact CSV names; Time is automatic
validation:
  minimum_speed_mps: 1.0          # optional movement acceptance
```

Semantic rules enforced by `scenario_schema.validate_scenario`: dt/duration
positive, finite, integral step count (dt is a default, not a hard limit);
maneuver times start at 0, strictly increase, stay within duration; outputs
must be registered channel names (unknown units fail closed); scalar override
keywords are upper-case tokens with finite values and may not duplicate a
typed vehicle field or touch protected run keywords (TSTEP, TSTOP, ...).

## Bind the base once

```bash
python scripts/base_registry.py --registry bases.local.json --name distributed_ev \
    --base "C:/work/Run_all.par" --version 2024.0 --run-control "<id>" --vehicle "<name>"
```

Resolving re-verifies the SHA256 on every run; a changed base fails instead of
silently switching vehicles. Legacy `vehicle_registry.py` registries keep
resolving (compat wrapper).

## Compile and run

```bash
python scripts/scenario_runner.py examples/scenarios/basic_cruise.yaml \
    --registry bases.local.json --out runs          # compile only
python scripts/scenario_runner.py ... --out runs --run   # + solver + validation
```

Compile writes the scenario directory (`base_Run_all.par` snapshot,
`override.par`, `simfile.sim`) and runs compile-time checks: TSTEP equals
EXT_MODEL_STEP, 64-bit DLLFILE pinned, PRODUCT_VER matches the pinned base
version, WRT list non-empty, base hash unchanged. `--run` then calls the
solver, validates the results (see run-validation.md) and finalizes
`run_manifest.json`.

## Artifacts

One directory per scenario: `run_manifest.json`, `base_Run_all.par`,
`override.par`, `simfile.sim`, then after `--run`: `run.csv` (native CarSim
units, 1 kHz), `run_echo.par`, `run_log.txt`, `solver_stdout.txt`. The
manifest records run status/timestamps, CarSim version + solver/DLL hashes,
base name + SHA256, the exact scenario config, artifact paths and input/output
hashes. It contains no research fields; `experiment_runner`'s manifest.json is
a research extension of the same compile path.
