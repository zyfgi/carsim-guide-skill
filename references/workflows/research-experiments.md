# Research experiment contract (schema v1)

Use this route for datasets, mass/CG/inertia identification, tire-force estimation,
or PINN/EKF experiments. Keep low-level batch/co-simulation helpers for advanced
controller integration. This runner generates data; it does not invent a learning
objective, train a network or establish parameter identifiability.

## Bind the vehicle once

Inspect the GUI-expanded base's Run Control, assembly and powertrain first.
`setup_paths.py` lists candidates but never selects the latest file. Create a
machine-local JSON registry, outside versioned experiment definitions:

```bash
python scripts/vehicle_registry.py --registry vehicles.local.json --name distributed_ev --base "C:/work/Run_all.par" --version 2024.0 --run-control "<name or UUID>" --powertrain "<verified powertrain>"
```

The binding records the absolute base path and SHA256. A changed base fails;
bind a new name to deliberately adopt a new revision. The runner also checks
the pinned CarSim version against standard install directory names. For custom
directory names the explicit registry version is used. This is version selection,
not a compatibility guarantee for releases other than those actually tested.

## Define and execute

Start with `examples/basic_run.yaml`, `parameter_sweep.yaml`,
`tire_force_estimation.yaml` or `vehicle_parameter_id.yaml`. All are executable
schema-v1 templates after binding the `distributed_ev` vehicle name.

```bash
python scripts/experiment_runner.py examples/basic_run.yaml --registry vehicles.local.json --out runs
python scripts/experiment_runner.py examples/basic_run.yaml --registry vehicles.local.json --out live_runs --run
```

Without `--run` only compile and inspect. Use a new output root or experiment ID
when executing afterward: every experiment directory is exclusive, including dry
runs. Runtime paths resolve from explicit `--prog/--datadir`, environment, then
the setup cache. Every critical path must exist.

`schemas/experiment.schema.json` rejects unknown keys. Python validation adds:

- `SimulationConfig.dt` and `duration` in seconds; positive finite values and an
  integral number of steps. Both generated files use exactly the same dt.
- `road.mu` in (0, 2]; current compiler supports a uniform road friction strip.
- `VehicleOverrides` in kg, metres and kg*m^2. `sprung_mass_kg` is an absolute
  sprung mass, not added payload or whole-vehicle mass. CG coordinates belong to
  the sprung body. Physical plausibility bounds depend on the chosen vehicle.
- Speed profiles in km/h and steering-wheel profiles in degrees, as the keys say.
  Times start at zero, strictly increase and stay within duration. Flat extrapolation
  holds the last value when a table ends early.
- Outputs use exact CSV signal names, e.g. `Roll`, not WRT alias `ROLL`. Time is
  automatic. Estimator and evaluator channels are explicit; an estimator cannot
  request a truth channel. Do not put unknown hardware channels in the registry
  without checking native CSV units for the actual base/version.
- Each configured sensor channel belongs to the estimator whitelist and is covered
  exactly once. Sensor settings are in SI; split groups when precision/units differ.
- Optional `sweep` is a list of named variants overriding only `road` and/or
  `vehicle_parameters`. Each variant has its own directory and resolved config.
  Seed is shared across variants to permit paired comparisons.

## Artifacts and acceptance

`manifest.json` records resolved configuration, seed, base/version/Run Control,
runtime paths and CLI/DLL hashes, Python/package versions (including torch when
installed), git commit/status, source hashes, input hashes and run status.
It distinguishes `compiled`, `running`, `passed` and `failed`. Failure retains the
reason and never presents missing/invalid results as accepted estimator data.

After solver termination, `validate_run.py` requires fresh nonempty CSV and echo,
finite numeric output, exact sample count, a strictly increasing requested time
grid through TSTOP, requested channels, and matching echoed timing and typed
vehicle parameters. An optional `minimum_speed_mps` tests actual movement; omit
it for stationary experiments. These checks run after the CLI finishes because
the batch interface does not expose a separate parse-only phase.

Accepted runs write `observable.csv` and `truth.csv`, both **already SI**. They
also write `sensor_<name>.csv` when configured. Read these artifacts with pandas;
`load_run()` is only for the native `run.csv`, otherwise conversion happens twice.
The manifest records per-channel units and hashes of generated output artifacts.

A base snapshot plus hash protects against changing that file. Referenced external
roads, tire files and other assets still need archiving with their original relative
layout for portable reproduction. The manifest is an audit trail, not a complete
CarSim installation/license bundle. Scenario acceptance checks structural execution;
physics adequacy, excitation, observability and training success remain separate.

## Migration from the old API

Core `read_run_csv()` returns every registered channel — tire outputs included —
in SI (`units="native"` for raw CarSim values); unknown units still fail and
missing requested columns still raise. Estimator isolation is this workflow's
responsibility, not the core reader's: use `load_run(...,
estimator_channels=[...])` plus `estimator_view()`/`evaluator_view()`. The old
core-level `allow_truth=` argument is a deprecated no-op. Motor speed is rad/s,
not rpm. Legacy unbound newest-base caches need explicit rebinding. Unknown install
directory versions require `product_version`. `extra_lines` remains a deprecated
alias of `unsafe_extra_lines`; neither may override typed timing or duplicate a
typed vehicle parameter. Research YAML intentionally has no raw keyword escape.
