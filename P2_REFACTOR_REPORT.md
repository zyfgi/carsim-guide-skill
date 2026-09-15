# CarSim Guide Skill P2 refactor report

Date: 2026-09-15

Status words in this report are deliberately separate:

- **Implemented**: code/docs exist and were inspected.
- **Unit-tested**: synthetic/local automated tests passed.
- **CarSim-tested**: a licensed real solver completed the relevant path.
- **Agent-behavior-tested**: a fresh target-model session completed the prompt.

## 1. P2 completed capabilities

Implemented: output and parameter discovery, typed simple table/dataset
reference overrides, Cartesian/zip batches, dependency graphs, control-mode
semantics, layered diagnostics, and explicit version compatibility status.
Discovery candidates are never silently promoted to verified facts. DATADIR
search and dataset references remain read-only and scoped.

The P1.1 gate was also completed: the `VehicleOverrides` field-name error was
fixed, scalar echo policies were added, database roots cannot escape DATADIR,
the Run Control/execution-context meaning replaced “one base per vehicle,” and
regression tests were added.

## 2. New Core APIs

| Module | Main API | Status |
|---|---|---|
| `output_registry.py` | `OutputSpec`, `resolve_output_alias`, `find_output_candidates` | implemented, unit-tested |
| `parameter_discovery.py` | `ParameterCandidate`, `discover_parameter`, `format_discovery_report` | implemented, unit-tested |
| `parameters.py` | `TableOverride`, `ReferenceOverride`, `RawOverride`, echo policies | implemented, unit-tested |
| `batch_runner.py` | `expand_sweep`, `apply_combination`, `run_batch` | implemented, unit-tested with mocked scenario execution |
| `database_tools.py` | `build_dependency_graph`, `format_dependency_tree` | implemented, unit-tested |
| `control_modes.py` | `ControlSpec`, `select_external_mode` | implemented, unit-tested |
| `diagnostics.py` | `Diagnostic`, `DiagnosticResult`, `diagnose_run` | implemented, unit-tested |
| `carsim_errors.py` | stable exception taxonomy | implemented, exercised by tests |
| `version_compatibility.py` | `CarSimVersion`, `compatibility_status`, `supports` | implemented, unit-tested |

`result_contract.py` remains a compatibility façade; the output registry and
discovery logic now live in `output_registry.py`.

## 3. Output discovery workflow

Exact verified name/alias → artifact search → evidence-bearing candidate →
native-unit/identity verification → registry entry → scenario request → fresh
CSV verification. Unknown natural-language text returns no inferred name.

`read_run_csv(path, columns=[...])` validates/converts only requested columns;
an unrequested unknown custom output no longer breaks subset reads. Full reads
still fail on any unknown retained channel.

## 4. Parameter discovery workflow

The implemented order is exact registry, verified alias, exact keyword search,
dataset identity/free text, dependency restriction, echo inspection, then
unresolved. Confidence is categorical (`verified`, `strong`, `weak`). Only
registry/alias proof sets `report.resolved`; ambiguity stays visible.

## 5. Override types

- `ScalarOverride`: finite native-unit value with `required`, `best_effort`, or
  `none` echo validation.
- `TableOverride`: non-empty finite rectangular table; optional monotonic time.
- `ReferenceOverride`: unique exact `#FullDataName` inside DATADIR; arbitrary
  paths rejected.
- `RawOverride` / `unsafe_extra_lines`: explicit advanced-syntax escape hatch;
  no semantic or complex echo guarantee.

Core timing, output-file, DLL, database-path, and product-version fields are
protected. Explicit port lines remain available to the already verified
Simulink/torque-control escape hatch.

## 6. Batch runner example

`examples/batches/friction_sweep.yaml` and
`examples/batches/mass_friction_grid.yaml` demonstrate Cartesian sweeps.
`batch_runner` creates `run_0001`, `run_0002`, …, delegates each to
`scenario_runner`, retains its scenario/run manifest, and maintains
`batch_manifest.json`. Default failure isolation and `--fail-fast` are tested.

## 7. Dataset dependency graph example

`examples/discovery/dataset_tree.py` renders parsed PARSFILE edges. Graph nodes
carry path/name/category; issues retain cycle, missing reference, duplicate
dataset, depth-limit, and external-reference evidence. No vehicle/subsystem
shape is hardcoded.

## 8. Diagnostics taxonomy

Exception classes cover environment/not-found/license, base/dataset/parameter,
scenario/compile, solver execution/termination, output missing/parse/channel,
echo, co-simulation, and version compatibility.

Diagnostics use fixed layers: environment, base, scenario, compile, solver,
license, output, echo, database, cosim, and version. The CLI recognizes only
stable signatures such as missing executable/DLL, DLL bitness mismatch,
license failure, absent termination, missing/stale CSV, echo mismatch, and an
unverified version.

## 9. Version compatibility status

CarSim 2024.0 is the only registry entry with prior field evidence. An explicit
newer version is accepted as detected-but-unverified; the generic route is
attempted and the warning/verified-feature list is written to the run manifest.
Parsing a version is never reported as compatibility proof.

## 10. Added tests

39 P2 tests were added across output/parameter discovery, subset CSV reading,
structured overrides, batch combinations/isolation/manifests, dependency graph
conditions, controls, diagnostics, compatibility, DATADIR scoping, P1.1 field
messages, and echo policy. Total repository collection: 140 tests.

## 11. Test results

- Full unit suite: **140 passed in 2.34 s**.
- Evidence record: `evals/results/2026-09-15-p2-unit-final.json`.
- Combined unit + licensed solver suite: **143 passed, 1 skipped in 4.58 s**.
- Licensed evidence record: `evals/results/2026-09-15-p2-functional-final.json`.
- Skill structure validator: **valid**.
- New P2 modules/tests/examples Ruff check: **passed**.
- Python bytecode compilation and JSON schema/eval parsing: **passed**.

Status: implemented and unit-tested. These results are not CarSim solver proof.

## 12. Fresh-agent behavior eval results

Eight P2 cases were added to `evals/evals.json` (unknown output, unknown and
ambiguous parameter, friction sweep, runtime feedback, ordinary tire outputs,
database safety, and unknown version).

Current status: **not agent-behavior-tested in a fresh GLM-5.3-Flash session**.
That model/session facility is not available in this execution environment.
No manual reading of the expected answers is presented as an independent eval.
The pre-existing P1 manual assessment remains separate.

## 13. Actual CarSim solver test results

The local 2024.0 PROG, DATADIR, explicit base binding, and solver license were
available. The solver-in-loop suite completed on 2026-09-15:

- Constant four-wheel torque import passed real vehicle acceleration and
  echoed/observed drive-torque checks.
- Open-loop throttle followed by braking passed real acceleration/deceleration
  checks.
- Speed-table replacement passed the real `run_echo.par` row check.
- The Simulink end-to-end test was skipped because `CARSIM_MATLAB` was not
  configured.

Status: the CarSim 2024.0 CLI route and the three existing control/echo paths
are **CarSim-tested**. P2 discovery decisions, `TableOverride`,
`ReferenceOverride`, and multi-run `batch_runner` behavior remain unit-tested
but were not each given a dedicated licensed solver scenario.

## 14. Still-unverified keywords/features

- The channel for front-suspension vertical travel is intentionally not
  registered; it requires discovery and local unit verification.
- Front spring/steering stiffness keywords are intentionally not added to the
  verified parameter registry.
- Generic structured table and dataset-reference serialization have unit tests
  but no licensed solver result yet.
- Non-2024.0 releases, VS API end-to-end stepping, and version-specific syntax
  differences remain unverified.
- Simulink P2 control abstraction did not receive a new end-to-end run.

## 15. P3 recommendations

1. Run the eight P2 prompts independently in the requested fresh model and
   archive raw responses/verdicts without exposing expectations beforehand.
2. Add dedicated licensed scenarios for TableOverride, ReferenceOverride,
   batch isolation, and diagnostics; configure `CARSIM_MATLAB` for the
   Simulink end-to-end check.
3. Register new output/parameter aliases only from those artifacts, with unit
   source and focused regression tests.
4. Consider a deletable read-only database index only after measured search
   latency justifies it.
