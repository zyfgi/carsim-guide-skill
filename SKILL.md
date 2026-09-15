---
name: carsim-guide
description: Operate and automate CarSim simulations from an agent, including safe output and parameter discovery, named Run Control execution contexts, structured overrides, isolated batch sweeps, dataset dependency inspection, control-mode selection, result validation, diagnostics, and version-aware CLI/Simulink/VS API routing. Use for executing, configuring, exploring, or debugging CarSim. Do not use for vehicle-dynamics theory alone, generic dataframe work, or unrelated simulators.
---

# CarSim agent router

CarSim 2024.0 is the verified solver target. Other explicitly detected
versions follow the generic path with an **unverified** warning; version
detection alone is not solver compatibility proof.

## Route the request

Read only the references needed for the current task.

When this skill provides a verified script path, prefer it over ad-hoc direct
manipulation. This is a routing preference, not a ban on evidence-gathering
tools or on a documented escape hatch.

| Request | Read / run |
|---|---|
| First use or paths moved | `scripts/setup_paths.py`; then `references/python-interface.md` |
| YAML scenario, manifest, validation | `references/scenarios.md`; `scripts/scenario_runner.py` |
| Unknown output or channel | `references/outputs-and-units.md`; `scripts/output_registry.py` |
| Known output units / SI conversion | `references/outputs-and-units.md` |
| Unknown physical parameter or keyword | `references/parameter-discovery.md`, then `references/database-exploration.md` |
| Scalar, table, or dataset-reference override | `references/parameters.md`; `scripts/parameters.py` |
| Multiple runs / parameter sweep | `references/batch-workflows.md`; `scripts/batch_runner.py` |
| Dataset dependencies / missing link / cycle | `references/database-exploration.md`; `build_dependency_graph()` |
| Choose batch, Simulink, or VS API control | `references/control-modes.md` |
| Throttle, brake, per-wheel torque syntax | `references/advanced-controls.md` |
| Unexpected run failure | `references/troubleshooting.md`; `scripts/diagnose_run.py` |
| CarSim compatibility / version status | `references/compatibility.md`, then `references/version-compatibility.md` when diagnosing version handling |
| Simulink closed loop | `references/simulink-cosim.md` |
| Low-level VS API stepping | `references/vs-c-api.md` |
| Read `.par` syntax | `references/dataset-syntax.md` |

## Non-negotiable execution model

- A base is one GUI-expanded `Run_all.par` for a specific **Run Control /
  execution context**, not merely a vehicle. Bind it by name and SHA256 with
  `base_registry.py`; never select the newest file.
- The CLI consumes the expanded base plus a later `override.par`. Do not point
  the solver at a thin hand-written tree of raw database datasets.
- Keep DATADIR read-only. Put scenarios, overrides, results, caches, and
  manifests outside it. A user request to change a database parameter should
  use an override or an explicitly cloned GUI dataset.
- `scenario_runner.py` owns the normal solver chain. `batch_runner.py` calls it
  once per isolated run; it does not implement another solver path.
- Results are valid only after fresh-artifact, termination, required-channel,
  finite time-grid, and applicable echo checks. Use `read_run_csv`; SI is the
  default.

## Discovery discipline

Discovery answers “what might this be”; verification answers “what did CarSim
actually use.” Never merge those states.

1. Classify output, parameter, dataset, execution mode, and validation need.
2. Resolve an exact verified registry entry or alias when one exists.
3. Otherwise normalize the physical query into explicit search terms and
   search supplied run/echo/database artifacts deterministically. Empty search
   terms mean unresolved; they must never match every artifact line.
4. Preserve all credible candidates and report ambiguity; never choose the
   first weak match or invent a keyword/channel.
5. Verify units and context in the actual dataset/echo before compiling.
6. After execution, verify the fresh CSV and echo and retain the manifest.

## Overrides and controls

- `VehicleOverrides`: five verified sprung-body fields, SI input.
- `ScalarOverride`: native-unit scalar plus echo policy `required`,
  `best_effort`, or `none`.
- `TableOverride`: finite rectangular simple table; optional strictly
  increasing time column.
- `ReferenceOverride`: exact `#FullDataName` resolution inside DATADIR; it does
  not accept arbitrary paths.
- `RawOverride` / legacy `unsafe_extra_lines`: explicit escape hatch with no
  complex semantic or echo guarantee.
- Core-managed runtime keywords (`TSTEP`, `TSTOP`, `IPRINT`, paths, DLL,
  product version, ports, and related simfile fields) are protected.

Distinguish targets from actuator commands: `speed_target` is not
`throttle_command`; `steering_target`, steering-wheel angle, and road-wheel
angle are different semantics. Prerecorded tables and batch replay are not
closed loop. Runtime feedback requires Simulink or VS API stepping.

## Version and failure handling

`version_compatibility.py` records only versions with real evidence. For a
new version: detect it, mark it unverified, try the generic compatible route,
and record the warning in `run_manifest.json`. Reject only malformed/unknown
version identity or a proven incompatible feature.

Classify failure at the layer where evidence places it: environment, base,
scenario, compile, solver, license, output, echo, database, cosim, or version.
Do not hide solver exceptions or over-parse unfamiliar solver text.

## Fixed conventions

- Vehicle frame: x forward, y left, z up; positive yaw rate is a left turn.
- Corners: L1=FL, R1=FR, L2=RL, R2=RR.
- One immutable directory per run; never overwrite prior batch members.
- Tire Fx/Fy/Fz/Kappa/Alpha are ordinary outputs.
- `Lat_Veh` and `Lat_Targ` remain excluded as verified drift artifacts; use
  Yo/Yaw for lateral position.
