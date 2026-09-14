# P1 refactor report — generic scenario layer + database exploration

Scope: the P1 plan (Gate 0 → scenario schema → base registry → parameters →
database tools → scenario runner → run manifest → run validation → research
compatibility → docs → tests → eval definitions). Commit-by-commit, tests green
before each next step. Nothing was pushed as part of this round unless asked.

## 1. Modified files

| File | Change |
|---|---|
| `scripts/result_contract.py` | Gate 0: `Channel.role` deleted — core now describes only native unit, SI unit, scale, category, source |
| `scripts/workflows/estimator_validation.py` | owns the privileged marking (`PRIVILEGED_PREFIXES`, `is_privileged`) and enforcing policy (`no_privileged_channels`; `no_truth_channels` kept as deprecated alias); `load_run` partitions via the workflow policy, not registry metadata |
| `scripts/scenario_schema.py` | now purely generic: `SimulationConfig`, `VehicleOverrides`, `validate_scenario`/`load_scenario` for the generic YAML; research validation moved out |
| `scripts/experiment_runner.py` | hosts research `validate_experiment`/`load_experiment` (moved from scenario_schema); compiles **through** `scenario_runner.compile_scenario`/`verify_compiled` — one compile path; manifest.json kept as the research extension format |
| `scripts/vehicle_registry.py` | deprecated compatibility wrapper over `base_registry` (`bind_vehicle`/`resolve_vehicle` delegate; legacy "vehicles"-shaped registry files keep resolving) |
| `scripts/carsim_batch.py`, `scripts/setup_paths.py` | import `sha256`/`product_version` from `base_registry`; `override_par` accepts `scalar_overrides=()` with protected-keyword conflict checks |
| `scripts/validate_run.py` | `ValidationIssue` + `RunValidationResult` + `check_run` (structured severities; missing run_log = warning; solver stdout termination check); `validate_run` kept as a raising compat wrapper |
| `SKILL.md`, `README.md` | routing rows for YAML scenarios, unknown keywords, run validation; capability + layout tables updated |
| `references/database-exploration.md` | new §0: the `database_tools` read-only API (grep recipes retained) |
| `evals/evals.json`, `evals/README.md` | +`beh-7-generic-scenario-yaml`, +`beh-8-base-ambiguity-newest` (defined; not yet run in fresh sessions) |
| `.github/workflows/ci.yml` | parse list covers the new modules |

## 2. New files

- `scripts/scenario_runner.py` — generic entry: YAML → base registry (name +
  SHA256, never newest) → compile (delegates to `carsim_batch.make_scenario`)
  → compile-time checks → optional solver run → `check_run` → `run_manifest.json`
- `scripts/base_registry.py` — `bind_base`/`resolve_base` (+CLI), `sha256`,
  `product_version`
- `scripts/parameters.py` — `ParameterSpec`, verified-only
  `PARAMETER_REGISTRY` (the five sprung-mass keywords), `ScalarOverride`,
  `PROTECTED_KEYWORDS`, `coerce_scalar_overrides`, `check_conflicts`
- `scripts/database_tools.py` — read-only exploration: `find_datasets`,
  `get_dataset_identity`, `get_parsfile_links`, `resolve_dataset_tree`
  (cycle-safe, depth-limited), `find_keyword`, `search_database_text`,
  `inspect_echo_keyword` (+CLI)
- `schemas/scenario.schema.json` — generic scenario v1 (no estimator/
  evaluator/sensors keys; tire channels are legal outputs; road key is
  `friction`)
- `references/scenarios.md`, `references/parameters.md`,
  `references/run-validation.md`
- `examples/scenarios/` — basic_cruise, friction_change, steering_maneuver,
  tire_force_output, vehicle_override (all schema-validated)
- `tests/test_p1_generic.py`, `tests/test_database_and_parameters.py`,
  `tests/test_scenario_runner.py`

## 3. Core API changes

- Generic scenario YAML is the configuration surface (`road.friction`, `base.name`,
  `parameters[]`); `SimulationConfig`/`VehicleOverrides` unchanged.
- `check_run`/`RunValidationResult` is the structured validation API.
- Core registry carries no estimator semantics; dependency direction is now
  enforced by a full-AST test (`test_core_modules_never_import_workflow_layer`).

## 4. Compatibility wrappers / deprecated API

- `vehicle_registry.bind_vehicle`/`resolve_vehicle` → `base_registry`
  (legacy "vehicles" registry sections still resolve; `powertrain` field
  mirrored).
- `validate_run(...)` raises on first error and returns the legacy metrics
  dict (now including an `issues` list).
- `no_truth_channels` → alias of `no_privileged_channels`.
- `extra_lines` (deprecated alias) and `read_run_csv(..., allow_truth=...)`
  (deprecated no-op) unchanged from P0.

## 5. Generic scenario example

See `examples/scenarios/basic_cruise.yaml` (reproduced in
references/scenarios.md). One YAML fully describes base, timing, road
friction, maneuver, vehicle parameters, scalar overrides and outputs.

## 6. Database exploration example

```python
import database_tools as db
db.find_keyword(datadir, "FS_COMP_COEFFICIENT")
# -> [{'path': .../Suspensions/Compliance_Front_Spring.par, 'full_data_name':
#     'Front Coil Spring 27 N/mm', 'count': 1, 'first_line': 'FS_COMP_COEFFICIENT 27'}]
db.inspect_echo_keyword("run_echo.par", "M_SU")   # [{'value': 1254.0, 'comment': 'sprung mass kg', ...}]
```

## 7. Run manifest example (core fields)

`run_manifest.json`: `manifest_version`, `run{id,created/started/finished,status}`,
`carsim{version,prog,datadir,solver,solver_sha256,dll,dll_sha256}`,
`base{name,base_run_all,sha256}`, `scenario` (exact config), `artifacts`,
`input_sha256`/`output_sha256`, `validation{passed,issues,metrics}`,
`provenance{python,platform,git_commit}` (git best-effort, never fatal). No
research fields — `experiment_runner`'s `manifest.json` is the research
extension.

## 8. Tests and results

101 tests pass (`python -m pytest tests/ -q`), +27 vs the P0 baseline: generic
schema (7), base registry (4), parameters + database tools (12, synthetic DB
fixture, read-only snapshot check), scenario runner/manifest/validation (5,
fake solver). `ruff check --select E9,F` clean; CI structure checks extended.

## 9. Behavior eval status

`beh-7`/`beh-8` defined (16 evals total: 5 positive / 3 negative / 8
behavior). Not yet executed in fresh GLM sessions — the earlier round
(6 cases, recorded in evals/README.md) predates P1.

## 10. Real CarSim solver execution

Yes. One licensed end-to-end run of `scenario_runner` on
`examples/scenarios/basic_cruise.yaml` via the local bound registry:
status `passed`, 10001 samples (10 s @ 1 kHz), compile checks clean,
echo validation confirmed `TSTEP=0.001, TSTOP=10.0, IPRINT=1`, zero issues.

## 11. Unverified CarSim keywords

None introduced by P1 itself. `PARAMETER_REGISTRY` still contains exactly the
five verified sprung-mass keywords; `ScalarOverride` intentionally accepts
unregistered keywords (after explicit dataset/echo confirmation) and marks
them unverifiable in the manifest when the echo cannot carry them.

## 12. P2 TODO

Table-level echo validation (speed/steer/MU tables); relocating
`experiment_runner.py`/`sensor_replay.py` under `scripts/workflows/`;
exception taxonomy; scenario `sweep` support in the generic runner;
subset-scoped `read_run_csv` validation (from the behavior-eval findings).
