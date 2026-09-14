# Refactor report — P0: generalizing the skill beyond the research contract

Scope: P0 only, per the agent checklist (`SKILL Core 去论文化 / Core-Workflow 分层 /
Output API 去 truth 强制限制 / 同步 documentation / 修复旧 eval`). P1–P3 items are
listed as TODO at the end and were deliberately not started.

## 1. Files changed and why

| File | Change | Purpose |
|---|---|---|
| `scripts/result_contract.py` | `Channel` gains a core `category` (vehicle_state/wheel/tire/powertrain/control/steering/road/time/other); `role` repositioned as a workflow-layer marking; `load_run` docstring marked as the research-workflow entry point | Core registry describes CarSim output taxonomy; estimator semantics move to the workflow layer |
| `scripts/carsim_batch.py` | `read_run_csv(path, columns, units="SI")`: returns **every** registered channel (tire outputs included, no flags); `units="native"` returns raw CarSim values; `allow_truth` kept as a deprecated, warning no-op; explicitly requesting `Lat_Veh`/`Lat_Targ` raises with the drift rationale. Output constants renamed with legacy aliases: `OUTPUTS_DEFAULT` (was `OUTPUTS_OBSERVABLE`), `OUTPUTS_TIRE` (was `OUTPUTS_TRUTH`), `PRIVILEGED_PREFIXES` (was `TRUTH_ONLY_PREFIXES`); `make_scenario` default unchanged in behavior | Core reader no longer enforces estimator/truth separation; tire forces are ordinary outputs |
| `references/workflows/` (new) | `estimator-validation.md` and `research-experiments.md` moved here via `git mv`; both now state they are optional workflow contracts | Core vs workflow layering; ordinary CarSim users never need them |
| `references/channel-registry.md` | Rewritten as the core units+categories contract; role/estimator_view content reduced to a pointer to the workflow doc | De-paper-ized core documentation |
| `SKILL.md` | Task-routing table at top (core tasks first, optional workflows marked); description generalized (no PINN/estimator/identification triggers); §2 execution-mode boundary (batch vs Simulink vs VS C API vs replay); §4/§5 API rows and channel section rewritten; mistake #10 and fixed-convention #4 replaced with core-equivalent rules | Core skill reads as a general CarSim operation guide |
| `README.md` | Repositioned: capability table leads with core operation; "Optional research workflows" is its own section; migration note rewritten for the new reader semantics; repository layout updated | First page answers "what can this skill do for CarSim", not "how it serves a study" |
| `references/python-interface.md`, `references/advanced-controls.md`, `references/simulink-cosim.md` | Reader section rewritten; all deprecated `extra_lines` teaching replaced by `unsafe_extra_lines`; channel-partitioning text reframed as workflow marking | Docs no longer teach deprecated API |
| `examples/param_sweep.py` | Dropped `allow_truth=True` | Examples use the recommended API |
| `tests/functional_carsim.py` | `_run_scenario` passes `unsafe_extra_lines=` | No deprecation warnings in the verification suite |
| `tests/test_carsim_batch.py` | New regressions: `test_read_tire_force_allowed`, `test_read_run_csv_native_units`, `test_allow_truth_is_deprecated_noop`, unreliable-request case, alias identity test; SI-scale fixture now states 9.80665 | Checklist §21 P0 regression set |
| `tests/test_research_contract.py` | Isolation test renamed `test_estimator_truth_isolation_optional_workflow`; core-reader assertion flipped (tire outputs pass through; isolation only via workflow views) | Test names must say `optional`, not imply core behavior |
| `evals/evals.json` | `beh-2` no longer cites deprecated `extra_lines`; `beh-3` reworded (isolation = optional workflow, core may generate/read Fx); added `beh-5-tire-output-allowed` and `beh-6-unknown-keyword-search` | Old evals no longer encode paper-only correctness |
| `evals/README.md` | (no structural change needed; records below are historical and immutable) | — |

## 2. Layering result

- **Core** (`SKILL.md`, `setup_paths.py`, `carsim_batch.py`, `result_contract.py`
  registry/reader, core references): environment, database, scenario, solver,
  outputs, validation. Knows nothing about estimators; reads tire outputs freely.
- **Optional workflows** (`references/workflows/`, `experiment_runner.py`,
  `scenario_schema.py`, `sensor_replay.py`, `validate_run.py`, `vehicle_registry.py`,
  `load_run`/`estimator_view`): research contracts layered on top; workflow → core
  dependency only.

## 3. Compatibility

- `OUTPUTS_OBSERVABLE`, `OUTPUTS_TRUTH`, `TRUTH_ONLY_PREFIXES` remain importable as
  aliases (identity-tested).
- `read_run_csv(..., allow_truth=...)` still runs and returns the same data, with a
  `DeprecationWarning` (behavior change: the default now *includes* previously
  blocked channels; this is the intended P0 un-restriction).
- `extra_lines` remains a deprecated alias of `unsafe_extra_lines`.
- Research YAML/workflow behavior unchanged (68 pre-existing contract tests kept,
  38 of them in `test_research_contract.py`).

## 4. Verification (all executed this revision)

1. `python -m pytest tests/ -q` → **72 passed** (was 68; +4 net new regressions).
2. `ruff check --select E9,F .` → clean (CI parity).
3. Solver-in-loop `pytest tests/functional_carsim.py -v` on a licensed local
   CarSim 2024.0 → **3 passed, 1 skipped** (Simulink case; needs `CARSIM_MATLAB`).
4. Real end-to-end tire-output check on a freshly generated scenario: core reader
   returned Fx/Fy/Fz/Kappa/Alpha in SI with no flags; `units="native"` returned raw
   km/h/rpm values; `allow_truth=True` warned as deprecated.
5. Structure checks: SKILL.md 178 lines (<500), description 511 chars, evals
   5 positive / 3 negative / 6 behavior, unique ids.
6. Terminology sweep: no `PINN`/`estimator-visible`/`ground truth`/`never into`
   language in core docs; old `references/research-experiments.md`-style paths
   updated everywhere outside immutable historical evidence records.

## 5. TODO (deliberately not in P0)

- P1: `experiment` → `scenario/run` renaming (runner + schema + manifest),
  generic `ParameterOverride` system beyond `VehicleOverrides`,
  `database_tools.py` exploration helpers, `RunValidationResult` with
  fatal/warning/info levels.
- P2: module split (`carsim_results.py`/`scenario.py`/`validation.py`),
  unified exception taxonomy (`CarSimNotFoundError`…`CoSimulationError`),
  generic-scenario examples (`steering_maneuver.yaml`, `wheel_torque.yaml`),
  moving workflow scripts under `scripts/workflows/`.
- P3: broader keyword/dataset discovery, more version compatibility, more
  control interfaces.

## 6. Unconfirmed keywords

None introduced. All keywords used by P0 changes were already verified
(`WRT_*`, `TSTEP`, `EXT_MODEL_STEP`, `OPT_VS_FILETYPE`, import declarations).
