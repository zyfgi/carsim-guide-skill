---
name: carsim-guide
description: Run and control CarSim 2024.0 headless from scripts or agents - generate scenarios (speed/steering/friction/payloads), drive with open-loop inputs or per-wheel torque (torque vectoring, TCS), co-simulate with Simulink, and read SI-unit results. Field-tested; no GUI after a one-time base setup, no MCP required. Use for ANY CarSim task - headless/batch runs, VS solver CLI, override.par/simfile workflows, vehicle or dataset changes, CarSim-Simulink co-simulation, FSAE-style events (acceleration, braking) - but not for generic CSV/pandas work or other simulators.
---

# CarSim 2024.0 Runtime Mechanics & Operation Guide (field-verified)

Updated 2026-09-14. Everything marked "verified" ran for real — the checks ship in this repo (`tests/` unit + solver-in-loop suites, `evals/` trigger protocol). Paths are placeholders — `scripts/setup_paths.py` resolves them per machine.

**Where to look first** (supporting files load on demand — open only what the task needs):

| Task | Use |
|---|---|
| First task on a machine (or CarSim moved) | `scripts/setup_paths.py` — one-time discovery, caches install paths (§1) |
| Build/modify scenarios (tables, params, payloads) | §3 + §5; script API in §4 |
| Extend or debug the Python workflow | `references/python-interface.md` |
| Open-loop throttle/brake, torque imports, table replace/append rules | `references/advanced-controls.md` |
| Close the loop in Simulink (co-sim) | `references/simulink-cosim.md` + `scripts/cosim_model.m`, `scripts/tv_cosim.m` |
| Find vehicles / datasets / keyword units | §6 + `references/database-exploration.md` |
| Read or edit .par datasets | `references/dataset-syntax.md` |
| Runnable demos (sweep, Simulink, torque vectoring) | `examples/` |
| Hard real-time stepping (rare) | `references/vs-c-api.md` |
| DLL export symbols | `scripts/dump_dll_exports.py` |
| Reproduce the verification / trigger evals | `tests/` + `evals/` (protocol in `evals/README.md`) |

---

## 0. Quick start (fresh machine → first successful run)

0. **Discover & cache the install** (once per machine): `python scripts/setup_paths.py` — finds PROG / DATADIR / the newest GUI-expanded base, verifies CLI + 64-bit DLL, caches to `~/.carsim_guide_paths.json` (~1 s; `--json` prints a compact summary for later sessions).
1. **License**: keep the CarSim GUI open, or start `<PROG>\Programs\cslm.exe`.
2. **Get a base (once per vehicle — the ONLY GUI step)**: open a Run Control → **Run Math Model** → take `Results\Run_<uuid>\Run_all.par` (setup_paths.py auto-picks the newest).
3. **First run** (65 s straight cruise at 50 km/h) — no path arguments needed:
   ```
   python scripts/carsim_batch.py --out <scenario dir> \
       --tstop 65 --speed-profile "0:50,65:50" --run --read
   ```
4. **Acceptance**: stdout ends with `Termination at simulation time = 65 s`; `<out>/run.csv` exists (1 kHz CSV).

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
| `base_run_all` | newest `<DATADIR>\Results\Run_*\Run_all.par` (+ `other_bases` list) |
| `matlab` | optional — Simulink co-sim examples |

**Flow**: first task on a machine → run `scripts/setup_paths.py`. Every later session resolves paths automatically (explicit argument > env `CARSIM_PROG`/`CARSIM_DATADIR`/`CARSIM_BASE` > cache) — all scripts and examples just work, and `python scripts/setup_paths.py --json` re-prints the cached paths in one line. **Never grep the filesystem for CarSim paths again**: if a run fails on paths, re-run setup (it revalidates the cache), fix one key with `--set prog=…`, or rescan with `--refresh` / reset with `--forget`.

**Pitfall**: the official `Programs\Python\vs.py` / `_vs` extension **segfaults** on import — never use it.

---

## 2. Overall run model (two falsified misconceptions)

The GUI's Run expands database datasets into Run_all.par, then calls the solver DLL. The CLI wrapper only does the second step. Data flow: `simfile.sim` → `INPUT` parsfile (base + overrides) → parse → integrate → `ERDFILE` CSV.

- **Misconception 1 (falsified)** — the solver cannot recursively parse raw database .par files (GUI-only decorations; deterministic segfault at the hanging-damper dataset). One GUI base per vehicle, then override everything. Never hand-write thin parsfiles; never write your own expander.
- **Misconception 2 (demoted)** — online validation does NOT require VS C API stepping. A 1 kHz CSV batch + causal replay by arrival time satisfies the "only arrived observations" constraint and is 16×+ faster.

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
<extra_lines: parameter overrides, e.g. M_SU / Y_CG_SU / IZZ_SU / RRE>
WRT_<channel> ...                               ! output whitelist
LOG_ENTRY / END
```

**simfile** (§3.2): `FILEBASE/INPUT/INPUTARCHIVE/ECHO/FINAL/LOGFILE/ERDFILE` + `PROGDIR/DATADIR/PRODUCT_ID CarSim/PRODUCT_VER 2024.0/VEHICLE_CODE i_i/EXT_MODEL_STEP/PORTS_IMP 0/PORTS_EXP 0/DLLFILE …\carsim_64.dll` (**always pin 64-bit**; GUI files may say 32-bit) + `END`. Exact template: `carsim_batch.simfile()`.

**Run** (§3.3): `"<PROG>\Programs\VS_SolverWrapper_CLI_64.exe" -sim <simfile>`. Success = stdout `Termination at simulation time = <TSTOP>` (RTIME lands in run_log.txt / run_end.par). Forward slashes on the command line — backslash escaping in Git Bash fails silently.

**Other CLI flags** (§3.4): `-par <expanded parsfile>`, `-uuid <Run uuid>`, `<simfile> -rundoc -imptxt -outtxt` (docs only; `-gen_run_all` does not work).

---

## 4. Python tooling (scripts/)

| API | Purpose |
|---|---|
| `scripts/setup_paths.py` | one-time install discovery → `~/.carsim_guide_paths.json`; later calls (`--json`) re-print it in one line |
| `make_scenario(out_dir, base_run_all=None, prog=None, datadir=None, tstop=65, speed_rows=None, steer_rows=None, mu=0.9, extra_lines=())` | writes override.par + simfile.sim, returns simfile path; path arguments default to the §1 cache; `extra_lines` injects parameter overrides (static payloads) |
| `run_solver(simfile_path, prog=None, timeout=600)` | subprocess CLI call (argv list + forward slashes), success-judged, raises with output tail; `prog` defaults to the cache |
| `read_run_csv(path, columns=None)` | pandas → **SI-unit** DataFrame (auto-drops unreliable columns, respects requested order) |
| `si_scale(col)` / `summarize(df)` / constants | column→SI factor (exact/underscore-delimited match); stats; `OUTPUTS_*`, `TRUTH_ONLY_PREFIXES`, `UNRELIABLE_COLS` |

CLI: `--out --tstop --speed-profile "t:v,…" --steer-profile "t:v,…" --mu --run --read --verbose` (`--prog --datadir --base` optional — §1 cache defaults). Runnable demos: `examples/param_sweep.py` (batch sweep), `examples/simulink_cosim.py`, `examples/torque_vectoring.py` (all resolve paths from the cache too; Simulink ones also take `--matlab`, cached as `matlab`).

---

## 5. Output channels and units (verified)

Recommended WRT set (`OUTPUTS_CORE/EXTRA` in the script): cg states (`Vx Vy Ax Ay AVz`), per-corner road-wheel steer + wheel speeds + drive/brake torques (`Steer_/AVy_/My_Dr_/My_Bk_{L1,R1,L2,R2}`), tire truths (`Fx_/Fy_/Fz_/Kappa_/Alpha_`), `ROLL PITCH`, motor speeds `AV_Mt_D1_*/D2_*`. Useful base columns: `Xo Yo Yaw Station Throttle SocBttry`.

**Unreliable**: `Lat_Veh`/`Lat_Targ` drift (up to 15 m) — lateral position from `Yo/Yaw`. **Slip quirk**: `Kappa_*` has a t≈0 normalization spike after a standing start (identical regardless of friction) — exclude t < 0.5 s when comparing slip.

Units → SI (built into `read_run_csv`): Vx/Vy km/h÷3.6; Ax/Ay **g**×9.81; AVz/angles deg×π/180; AVy_* **rpm**×2π/60; forces/torques already SI. Signs (verified): left turn → AVz>0; My_Dr + = drive, − = regen; My_Bk ≤ 0 forward. Corners: L1=FL, R1=FR, L2=RL, R2=RR.

**Parameter overrides** (§5.3, via `extra_lines`): `M_SU <kg>`, `IZZ_SU <kg·m²>`, `LX_CG_SU/H_CG_SU/Y_CG_SU <mm>`, `RRE/R0(axle,side) <mm>`. **Y_CG_SU quirk (A/B/C/D verified)**: static left-right load split is exactly linear in the value but ≈**2.07×** the naive rigid prediction; ground-truth lateral CG = the `Y_CG_TL` (CALC) line in `run_echo.par` — never invert the Fz split naively.

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
10. Truth isolation: Fx/Fy/Fz/Kappa/Alpha are simulator ground truth — evaluation only, never into an estimator.
11. Constant-valued speed table "disappears" from run_echo.par — it is auto-normalized to `SPEED_TARGET_CONSTANT`, not a failure.

---

## 8. Delegation & fallbacks (when NOT to use this workflow)

- **Base generation & human browsing** → VS Browser GUI (once per vehicle; §6).
- **MATLAB / Simulink co-simulation** → supported and verified when the controller lives in Simulink: `references/simulink-cosim.md`. For identification/data loops, stay with the CSV batch — 16×+ faster and MATLAB-free.
- **Hard real-time stepping** → only then consider the VS C API via ctypes: `references/vs-c-api.md` (prototype only, unverified end-to-end).
- **CarSim MCP, if configured** → optional exploration accelerator (`find_dataset`, `resolve_assembly`, `get_dataset`, `describe_keyword`); run/read always via the §4 scripts. Mapping + write-tool warning: `references/database-exploration.md` §6.

---

## 9. Fixed conventions (do not change)

- Body frame x forward / y left / z up; yaw rate r > 0 = left turn.
- Corners FL, FR, RL, RR (= L1, R1, L2, R2).
- One directory per scenario (~10 files: override.par / simfile.sim / run.csv / run_echo.par / run_log.txt …); batch runs never overwrite each other.
- Estimator-visible channels = whitelist only; ground-truth channels go to the evaluator.
