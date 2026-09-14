---
name: carsim-guide
description: Operate and automate CarSim simulations from an agent - configure and run CarSim scenarios, modify vehicle, road and run parameters, select and explore datasets, read simulation outputs and units, run batch simulations, apply throttle/brake/per-wheel-torque control inputs, debug solver problems, and run CarSim-Simulink co-simulation. Use for executing, configuring, debugging, or programmatically automating CarSim. Do not use for generic vehicle-dynamics theory, generic pandas work, or unrelated simulators.
---

# CarSim 2024.0 Runtime Mechanics & Operation Guide (field-verified)

Updated 2026-09-14. Everything marked "verified" ran for real — the checks ship in this repo (`tests/` unit + solver-in-loop suites, `evals/` trigger protocol). Paths are placeholders — `scripts/setup_paths.py` resolves them per machine.

**Task routing** (supporting files load on demand — open only what the task needs; research workflows are optional and never required for ordinary CarSim operation):

| Task | Use |
|---|---|
| First task on a machine (or CarSim moved) | `scripts/setup_paths.py` — one-time discovery, caches install paths (§1) |
| Run a scenario headless (batch) | §0–§3; script API in §4, walkthrough in `references/python-interface.md` |
| Vehicle / dataset selection & exploration | §6 + `references/database-exploration.md` |
| Change parameters (mass / CG / inertia / any keyword) | §5 (typed `VehicleOverrides`, `unsafe_extra_lines`) |
| Read output variables, units, SI conversion | §5 + `references/channel-registry.md` |
| Throttle / brake / per-wheel torque / table rules | `references/advanced-controls.md` |
| Batch runs / parameter sweeps | `examples/param_sweep.py` |
| Simulink closed-loop control | `references/simulink-cosim.md` + `scripts/cosim_model.m`, `scripts/tv_cosim.m` |
| Solver failure / diagnosis | §7 + `references/python-interface.md` §3 |
| Read or edit .par datasets | `references/dataset-syntax.md` |
| Hard real-time stepping (rare) | `references/vs-c-api.md` |
| DLL export symbols | `scripts/dump_dll_exports.py` |
| **Optional research workflows** (data generation with manifests, estimator validation, sensor replay, identification) | `references/workflows/research-experiments.md` + `references/workflows/estimator-validation.md` → `scripts/experiment_runner.py` |
| Runnable demos | `examples/` |
| Reproduce the verification / trigger evals | `tests/` + `evals/` (protocol in `evals/README.md`) |

---

## 0. Quick start (fresh machine → first successful run)

0. **Discover & cache the install** (once per machine): `python scripts/setup_paths.py` — finds PROG / DATADIR and lists candidate bases; verifies Data, CLI and DLL; caches paths to `~/.carsim_guide_paths.json` (`--json` prints a compact summary).
1. **License**: keep the CarSim GUI open, or start `<PROG>\Programs\cslm.exe`.
2. **Get a base (once per vehicle — the ONLY GUI step)**: open a Run Control → **Run Math Model** → take `Results\Run_<uuid>\Run_all.par`. Check vehicle/Run Control identity, then explicitly bind with `python scripts/setup_paths.py --set base_run_all="<absolute path>"` (records a SHA256). Never choose by modification time; research runs use a named vehicle registry instead (optional — see workflows reference).
3. **First run** (65 s straight cruise at 50 km/h) — no path arguments needed:
   ```
   python scripts/carsim_batch.py --out <scenario dir> \
       --tstop 65 --speed-profile "0:50,65:50" --run --read
   ```
4. **Smoke acceptance**: stdout ends with `Termination at simulation time = 65 s`; `<out>/run.csv` exists. The optional research workflow additionally runs `validate_run`: fresh CSV/echo, finite complete time grid, required channels and requested parameter echo (see workflows reference).

Daily runs end here — no GUI, no database writes, no Simulink, no C API.

---

## 1. Install paths: discover once, never explore again

`scripts/setup_paths.py` caches machine paths to `~/.carsim_guide_paths.json` — outside the skill, so nothing machine-specific can leak into a repo:

| Cached key | Item / typical value |
|---|---|
| `prog` | `<install root>\CarSim2024.0_Prog` |
| `datadir` | sibling `<install root>\CarSim2024.0_Data` (read-only) |
| `cli_solver` | `<PROG>\Programs\VS_SolverWrapper_CLI_64.exe` |
| `solver_dll` | `<PROG>\Programs\solvers\carsim_64.dll` (64-bit; full VS C API, 300+ symbols) |
| `license_manager` | GUI running, or `<PROG>\Programs\cslm.exe` headless |
| `base_run_all` | explicitly selected base, `base_sha256` + `base_selection`; `other_bases` lists candidates only |
| `matlab` | optional — Simulink co-sim examples |

**Flow**: first task on a machine → run `scripts/setup_paths.py`. Every later session resolves paths automatically (explicit argument > env `CARSIM_PROG`/`CARSIM_DATADIR`/`CARSIM_BASE` > cache) — all scripts and examples just work, and `python scripts/setup_paths.py --json` re-prints the cached paths in one line. **Never grep the filesystem for CarSim paths again**: if a run fails on paths, re-run setup (it revalidates the cache), fix one key with `--set prog=…`, or rescan with `--refresh` / reset with `--forget`.

**Pitfall**: the official `Programs\Python\vs.py` / `_vs` extension **segfaults** on import — never use it.

---

## 2. Overall run model (two falsified misconceptions)

The GUI's Run expands database datasets into Run_all.par, then calls the solver DLL. The CLI wrapper only does the second step. Data flow: `simfile.sim` → `INPUT` parsfile (base + overrides) → parse → integrate → `ERDFILE` CSV.

- **Misconception 1 (falsified)** — the solver cannot recursively parse raw database .par files (GUI-only decorations; deterministic segfault at the hanging-damper dataset). One GUI base per vehicle, then override everything. Never hand-write thin parsfiles; never write your own expander.
- **Misconception 2 (demoted)** — validating a controller against recorded data does NOT require VS C API stepping. Pick the execution mode by coupling: **CLI batch** when external inputs are fixed in advance (scenarios, sweeps, data generation); **Simulink co-simulation** when a controller must act on the vehicle inside the running sim; **VS C API** only for low-level stepping when Simulink doesn't fit. A 1 kHz CSV batch plus causal replay of sensor timing is 16×+ faster than stepping — but replay is data processing, not a closed loop.

---

## 3. The override.par pattern (core mechanism, verified)

CarSim parses parsfiles **last-write-wins**: reference the base first, then every keyword/table after it overrides the base. Skeleton (full annotated template: `references/python-interface.md` §1; the script generates it):

```
PARSFILE
PARSFILE <absolute path to base Run_all.par>   ! GUI-expanded base
OPT_ERROR_DIALOG 0 / OPT_ALL_WRITE 0 / OPT_VS_FILETYPE 4   ! headless + CSV output
TSTART 0 / TSTOP <s> / OPT_STOP 0 / SSTOP 100000 / TSTEP 0.001 / IPRINT 1
INSTALL_SPEED_CONTROLLER / OPT_SC 1 / OPT_BK_SC 1 / SPEED_TARGET_COMBINE ADD
SPEED_TARGET_TABLE LINEAR_FLAT                  ! rows: time s, km/h; initial speed = first row
  <rows> ENDTABLE
MU_ROAD_CARPET 2D_STEP                          ! friction override (low-mu base MUST be overridden)
  <s, mu_left, mu_right rows> ENDTABLE
OPT_DM 0 / OPT_STR_BY_TRQ 0 / STEER_SW_TABLE    ! open-loop steering — the ONLY reliable steering override
  <rows: time s, SW angle deg> ENDTABLE
<typed VehicleOverrides, or unsafe_extra_lines for advanced syntax>
WRT_<channel> ...                               ! output whitelist
LOG_ENTRY / END
```

**simfile** (§3.2): `FILEBASE/INPUT/INPUTARCHIVE/ECHO/FINAL/LOGFILE/ERDFILE` + `PROGDIR/DATADIR/PRODUCT_ID CarSim/PRODUCT_VER/VEHICLE_CODE i_i/EXT_MODEL_STEP/PORTS_IMP 0/PORTS_EXP 0/DLLFILE …\carsim_64.dll` (**always pin 64-bit**; GUI files may say 32-bit) + `END`. Version comes from a standard install directory name or explicit `product_version`; unknown versions fail instead of defaulting to 2024.0. `make_scenario(config=SimulationConfig(...))` uses the same dt for both generated files.

**Run** (§3.3): `"<PROG>\Programs\VS_SolverWrapper_CLI_64.exe" -sim <simfile>`. Success = stdout `Termination at simulation time = <TSTOP>` (RTIME lands in run_log.txt / run_end.par). Forward slashes on the command line — backslash escaping in Git Bash fails silently.

**Other CLI flags** (§3.4): `-par <expanded parsfile>`, `-uuid <Run uuid>`, `<simfile> -rundoc -imptxt -outtxt` (docs only; `-gen_run_all` does not work).

---

## 4. Python tooling (scripts/)

| API | Purpose |
|---|---|
| `scripts/setup_paths.py` | one-time install discovery → `~/.carsim_guide_paths.json`; later calls (`--json`) re-print it in one line |
| `make_scenario(..., config=SimulationConfig(dt, duration), vehicle_overrides=VehicleOverrides(...))` | writes override.par + simfile.sim from one timing config; legacy tstop/tstep accepted only without config; advanced syntax uses `unsafe_extra_lines` |
| `run_solver(simfile_path, prog=None, timeout=600)` | subprocess CLI call (argv list + forward slashes), success-judged, raises with output tail; `prog` defaults to the cache |
| `read_run_csv(path, columns=None, units="SI")` | core reader: every registered channel (tire outputs included), SI by default / `units="native"` for raw CarSim values; unknown units and missing requested channels fail |
| `load_run(path, estimator_channels=[...])` | **optional research workflow** (`scripts/workflows/estimator_validation.py`): role-partitioned SI views with estimator-whitelist isolation (`estimator_view` / `evaluator_view`) |
| `experiment_runner.py scenario.yaml --registry vehicles.json --out runs [--run]` | optional research workflow: typed schema → pinned base → manifest → solver, validation and sensor packets |
| `si_scale(col)` / `summarize(df)` / constants | column→SI factor (explicit registry lookup); stats; `OUTPUTS_CORE` (all channels incl. tire), `OUTPUTS_DEFAULT` (compact default), `OUTPUTS_TIRE`, `UNRELIABLE_COLS` |

CLI: `--out --tstop --speed-profile "t:v,…" --steer-profile "t:v,…" --mu --run --read --verbose` (`--prog --datadir --base` optional — §1 cache defaults). Runnable demos: `examples/param_sweep.py` (batch sweep), `examples/simulink_cosim.py`, `examples/torque_vectoring.py` (all resolve paths from the cache too; Simulink ones also take `--matlab`, cached as `matlab`).

---

## 5. Output channels and units (verified)

The registry in `scripts/result_contract.py` defines every supported channel with its native unit, SI factor and a category (vehicle_state / wheel / tire / powertrain / control / steering / road). `read_run_csv` returns all registered channels — tire outputs Fx/Fy/Fz/Kappa/Alpha are ordinary CarSim outputs, request them via `outputs=OUTPUTS_TIRE` when generating and read them like any other column. Unregistered channels (including Throttle/SocBttry until their source units are verified) fail closed instead of being scaled by a guess. Whether tire outputs may feed an estimator/learning algorithm is workflow-specific — see `references/workflows/estimator-validation.md`.

**Unreliable**: `Lat_Veh`/`Lat_Targ` drift (up to 15 m) — lateral position from `Yo/Yaw`. **Slip quirk**: `Kappa_*` has a t≈0 normalization spike after a standing start (identical regardless of friction) — exclude t < 0.5 s when comparing slip.

Units → SI: Vx/Vy km/h÷3.6; Ax/Ay **g**×9.80665; AVz/angles deg×π/180; wheel AVy_* and motor AV_Mt_* **rpm**×2π/60; forces/torques already SI. See `references/channel-registry.md` for scope. Signs (verified): left turn → AVz>0; My_Dr + = drive, − = regen; My_Bk ≤ 0 forward. Corners: L1=FL, R1=FR, L2=RL, R2=RR.

**Parameter overrides**: prefer `VehicleOverrides(sprung_mass_kg=..., cg_x_m=..., cg_y_m=..., cg_z_m=..., izz_kgm2=...)`; metres convert internally to CarSim mm. Sprung mass is not total vehicle mass; sprung-body CG is not total vehicle CG. Radius and advanced keywords remain in `unsafe_extra_lines` (old `extra_lines` is deprecated). **Y_CG_SU quirk (A/B/C/D verified)**: static left-right load split was ≈**2.07×** the naive rigid prediction on the tested base; the verified lateral CG value is `Y_CG_TL` (CALC) in the echo. This factor is not universal.

**Advanced controls** (§5.4): open-loop throttle/brake (`OPT_SC 0` — standstill start), per-wheel torque imports (GUI-native `Add 0.0! 1` form — `VS_REPLACE` is inert with ports active), table replace-vs-append rules — all in `references/advanced-controls.md`.

---

## 6. New vehicle / database exploration

The database is plain-text .par; grep covers everything (recipes in `references/database-exploration.md`): find datasets by `#FullDataName`, assembly trees via recursive `PARSFILE` lines, keyword units from `run_echo.par` → manuals → GUI. A run's actually-used datasets are listed in `run_log.txt`. Library map: `Vehicles\Assembly\` (entry), `Vehicles\Sprung_Mass\`, `Powertrain\`, `Procedures\`, `Runs\` (thin Run Controls — the base source), `Control\{Speed_t,Driver,Braking}\`, `Roads\{3D_Road,XY_Table,Friction}\`, `IO_Channels\I_Channels\`. Dataset IDs (UUIDs) differ per install — locate by name, never hardcode.

New vehicle: find it → clone a Run Control in the GUI → Run Math Model → new base → back to §3. Dataset internals: `references/dataset-syntax.md` (never hand-write thin parsfiles — Misconception 1).

**Convention**: database read-only; scenario files in your own directory, referencing DB datasets by absolute path.

---

## 7. Common mistakes (all field-tested — do not retry)

1. Thin parsfile referencing a vehicle assembly → solver segfault; hand-written expanders → whack-a-mole errors. Override pattern only.
2. `_vs` Python extension (vs.py) → segfault. Use the CLI / scripts.
3. Closed-loop `LTARG_TABLE` steering override → rows are **appended**, not replaced (phantom target observed). Open-loop `STEER_SW_TABLE` only.
4. Duplicate table abcissa → parse error; dedupe (`carsim_batch._dedupe`).
5. Backslash paths on the Git Bash command line → silent wrong-file runs ("results didn't change" — check the CSV timestamp).
6. GUI-generated simfile DLLFILE may be 32-bit → pin 64-bit.
7. No license → "Unable to load library"; start `cslm.exe` headless.
8. `OPT_ALL_WRITE 1` + long runs → GB-scale ERD; use the WRT whitelist.
9. CarSim MCP `set_dataset/set_table/set_link/write_parsfile` write DB files — under the read-only convention use override.par instead.
10. `Lat_Veh`/`Lat_Targ` in the WRT list → up to 15 m drift; derive lateral position from `Yo`/`Yaw` instead (the reader drops them).
11. Constant-valued speed table "disappears" from run_echo.par — it is auto-normalized to `SPEED_TARGET_CONSTANT`, not a failure.

---

## 8. Delegation & fallbacks (when NOT to use this workflow)

- **Base generation & human browsing** → VS Browser GUI (once per vehicle; §6).
- **MATLAB / Simulink co-simulation** → supported and verified when the controller lives in Simulink: `references/simulink-cosim.md`. When external inputs can be fixed before the run (open-loop profiles, sweeps, data generation), stay with the CSV batch — 16×+ faster and MATLAB-free.
- **Hard real-time stepping** → only then consider the VS C API via ctypes: `references/vs-c-api.md` (prototype only, unverified end-to-end).
- **CarSim MCP, if configured** → optional exploration accelerator (`find_dataset`, `resolve_assembly`, `get_dataset`, `describe_keyword`); run/read always via the §4 scripts. Mapping + write-tool warning: `references/database-exploration.md` §6.

---

## 9. Fixed conventions (do not change)

- Body frame x forward / y left / z up; yaw rate r > 0 = left turn.
- Corners FL, FR, RL, RR (= L1, R1, L2, R2).
- One directory per scenario (~10 files: override.par / simfile.sim / run.csv / run_echo.par / run_log.txt …); batch runs never overwrite each other.
- Database stays read-only: all changes go through scenario override files, never dataset edits.
- Results are read through the registry (`read_run_csv`), SI by default (`units="native"` opts out); unknown units fail instead of being guessed.
