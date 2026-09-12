---
name: carsim-guide
description: CarSim 2024.0 (VS Solver) runtime mechanics and headless scripting guide. Covers the override.par pattern (GUI-expanded base + keyword overrides), a self-contained simfile template, CLI batch runs, Python interface scripts (generate / run / read CSV), output channels and unit conversion, the VS C API (ctypes) fallback, database exploration, and a field-tested pitfall list. Self-contained - no CarSim MCP required. Use for ANY task involving CarSim, the VS solver, carsim_64.dll, simfile.sim, Run_all.par, ERD/CSV result reading, creating or modifying vehicle / procedure / road datasets, or running CarSim headless, in batch, or in closed loop - even if the user never mentions the runtime mechanics.
---

# CarSim 2024.0 Runtime Mechanics & Operation Guide (agent reference, field-verified)

Updated 2026-09-12. Everything marked "verified" was validated by actually running it (multi-scenario batch runs succeeded, RTIME≈0.05, roughly 17× real time; performance varies by machine). This skill is **self-contained**: no CarSim MCP dependency, no Simulink, no VS C API. Paths are not machine-bound — resolve the placeholders on the target machine.

**Companion files (read on demand, not upfront):**
- `scripts/carsim_batch.py` — full workflow script: generate override.par/simfile, run headless, read CSV
- `scripts/dump_dll_exports.py` — zero-dependency DLL export-symbol enumerator
- `references/python-interface.md` — read before modifying/extending carsim_batch.py (walkthrough + unit contract)
- `references/database-exploration.md` — read when finding vehicles / inspecting assemblies / looking up keyword units (grep-based, no MCP)
- `references/dataset-syntax.md` — read when you need to understand or edit database datasets (.par syntax templates)

---

## 0. Quick start (fresh machine → first successful run)

1. **Locate the installation**: find the CarSim install root (program dir `<PROG> = …\CarSim2024.0_Prog`, database `<DATADIR> = …\CarSim2024.0_Data`, sibling directories). Look in the Start Menu, running processes, or the GUI title bar.
2. **License**: keep the CarSim GUI open, or start `<PROG>\Programs\cslm.exe`. Without a license the solver (DLL/CLI) fails immediately.
3. **Get a base (once per vehicle — the ONLY step that needs the GUI)**: in the GUI, open a Run Control that references the target vehicle → click **Run Math Model** → take `Results\Run_<uuid>\Run_all.par` as the base. If no suitable Run Control exists, clone one (vehicle + procedure + camera, three PARSFILE lines — see references/database-exploration.md §5).
4. **Run the first scenario** (65 s straight cruise at 50 km/h):
   ```
   python scripts/carsim_batch.py --prog <PROG> --datadir <DATADIR> \
       --base <absolute path to base Run_all.par> --out <scenario dir> \
       --tstop 65 --speed-profile "0:50,65:50" --run --read
   ```
5. **Acceptance check**: stdout ends with `Termination at simulation time = 65` plus an `RTIME=...` line; the scenario directory contains `run.csv` (1 kHz text CSV).

Daily runs end here — **no GUI, no database writes, no Simulink, no C API**.

---

## 1. Key paths (placeholders — resolve on the target machine)

| Item | Path / value |
|---|---|
| Program root PROG | `<CarSim install root>\CarSim2024.0_Prog` |
| Database DATADIR (read-only) | `<CarSim install root>\CarSim2024.0_Data` |
| CLI solver wrapper | `<PROG>\Programs\VS_SolverWrapper_CLI_64.exe` |
| Solver DLL (64-bit) | `<PROG>\Programs\solvers\carsim_64.dll` (exports the full VS C API, 300+ symbols; dependent DLLs sit next to it) |
| License | a running GUI provides it; headless → run `Programs\cslm.exe` |
| Manual PDFs | `Help\Memos\` (VS_Commands_API, VS_SolverWrapper, Procedures_VS_Commands, …), `Help\Manuals\VS_SDK.pdf` |
| Python | bring your own Python 3.x (with pandas; conda/venv both fine). CarSim ships `Programs\Python\Python64` (3.10, no pip) |

**Major pitfall**: the official `Programs\Python\vs.py` depends on the `_vs` extension (i.e. `PyInit__vs` inside carsim_64.dll); importing it directly **segfaults**. Do not go down that road.

---

## 2. Overall run model (including two falsified misconceptions)

The VS solver is a pure computational DLL. The GUI's Run button does two things: ① **expands** the database datasets into Run_all.par; ② calls the DLL. The CLI wrapper only does ②.

**Misconception 1 (falsified by testing): the solver cannot recursively parse raw database .par files.**
Raw datasets contain GUI-only decorations (`SET_UNITS_TABLE_ROW`, `symbol_add`, `.ani` animator references, …). A thin parsfile referencing a vehicle assembly first fails with `SET_UNITS_TABLE_ROW ... doesn't exist`, and after cleaning, deterministically segfaults at the hanging-damper dataset; the same reproduces on a vehicle known to run. **Conclusion: the solver only accepts GUI-expanded content. The correct approach = generate a base Run_all.par once per vehicle via the GUI, then run every scenario through the override pattern (§3). Do not write your own expander.**

**Misconception 2 (demoted to fallback): online validation does NOT require step-by-step VS C API integration.**
The ctypes stepping prototype is sound (§8) but unnecessary — a 1 kHz CSV batch run + causal replay by arrival time (observations tagged with arrival_time) strictly satisfies the "only use observations that have arrived" online constraint, and is 16×+ faster.

Data flow: `simfile.sim` → `INPUT` parsfile (= base + overrides) → parse & build model → integrate → `ERDFILE` writes CSV output.

---

## 3. The override.par pattern (core mechanism, verified)

Principle: CarSim parses parsfiles **last-write-wins**. The first line of override.par pulls in the base; every keyword/table after it overrides the base's entry.

### 3.1 override.par (example: 65 s straight cruise at 50 km/h)

```
PARSFILE
PARSFILE <absolute path to base Run_all.par>  ! base: GUI-expanded Run_all.par
OPT_ERROR_DIALOG 0                         ! headless: never pop an error dialog
OPT_ALL_WRITE 0                            ! write only the WRT channels below
OPT_VS_FILETYPE 4                          ! ERD output as text CSV (key switch)
TSTART 0
TSTOP 65.0
OPT_STOP 0                                 ! disable stop-on-distance
SSTOP 100000
TSTEP 0.0010000                            ! 1 ms step
IPRINT 1                                   ! one CSV row per step -> 1 kHz
INSTALL_SPEED_CONTROLLER                   ! -- closed-loop speed control --
OPT_SC 1
OPT_BK_SC 1
OPT_SC_ENGINE_BRAKING 1                    ! EV: prefer regen braking on decel
SPEED_TARGET_CONSTANT 0
SPEED_TARGET_S_CONSTANT 0
SPEED_TARGET_COMBINE ADD
SPEED_TARGET_TABLE LINEAR_FLAT             ! rows: time s, speed km/h; initial speed = first row (verified)
0.000000, 50.000000
65.000000, 50.000000
ENDTABLE
MU_ROAD_CARPET 2D_STEP                     ! -- friction override (required when a low-mu base runs normal scenarios) --
0, -20, 20
-500, 0.900000, 0.900000
1000, 0.900000, 0.900000
ENDTABLE
OPT_DM 0                                   ! -- open-loop steering (the only reliable steering override) --
OPT_STR_BY_TRQ 0
STEER_SW_TABLE LINEAR_FLAT                 ! rows: time s, steering wheel angle deg
0.000000, 0.000000
65.000000, 0.000000
ENDTABLE
WRT_Vx                                     ! -- output channel declarations (CSV columns) --
WRT_Ax
WRT_Ay
WRT_AVz
! (full channel list in §5.1)
LOG_ENTRY anything
END
```

### 3.2 simfile.sim (self-contained; all output goes to the scenario directory)

```
SIMFILE
FILEBASE <scenario dir>/run
INPUT <scenario dir>/override.par
INPUTARCHIVE <scenario dir>/run_all.par
ECHO <scenario dir>/run_echo.par           ! parse echo: variable-verification evidence
FINAL <scenario dir>/run_end.par
LOGFILE <scenario dir>/run_log.txt         ! lists every dataset actually used
ERDFILE <scenario dir>/run.csv             ! OPT_VS_FILETYPE 4 -> CSV
PROGDIR <PROG>
DATADIR <DATADIR>
PRODUCT_ID CarSim
PRODUCT_VER 2024.0
VEHICLE_CODE i_i
EXT_MODEL_STEP 0.00100000
PORTS_IMP 0
PORTS_EXP 0
DLLFILE <PROG>\Programs\solvers\carsim_64.dll   ! always pin 64-bit (GUI-generated ones may say 32-bit)
END
```

### 3.3 Run (headless)

```
"<PROG>\Programs\VS_SolverWrapper_CLI_64.exe" -sim <absolute simfile path>
```

Success marker: stdout ends with `Termination at simulation time = <TSTOP>`; the `Computational time ratio: RTIME=...` line lands in `run_log.txt` / `run_end.par`, not stdout.
**Path style**: forward slashes `C:/...` are safest on the command line (backslash escaping in Git Bash fails silently — stepped on this; Python subprocess with an argv list avoids the issue).

### 3.4 Other CLI capabilities

```
VS_SolverWrapper_CLI_64.exe -par <expanded parsfile>        # use an expanded parsfile directly
VS_SolverWrapper_CLI_64.exe -uuid <Run_xxx-uuid>           # use a Run Control that has Results in the DB
VS_SolverWrapper_CLI_64.exe <simfile> -rundoc -imptxt -outtxt   # generate docs only, no run
#   -imptxt/-outtxt = Import/Export variable lists; -rundoc = Run_Doc.par
#   -gen_run_all does not work in practice (needs DB context)
```

---

## 4. Python tooling (scripts/carsim_batch.py)

Wraps the entire §3 workflow into three functions plus a CLI entry point (parameterized, no hardcoded paths):

| API | Purpose |
|---|---|
| `make_scenario(out_dir, base_run_all, prog, datadir, tstop, speed_rows, steer_rows, mu=0.9)` | writes override.par + simfile.sim, returns the simfile path |
| `run_solver(simfile_path, prog, timeout=600)` | calls the CLI via subprocess (argv list + forward slashes), judges success by `Termination at simulation time`, raises with the output tail on failure |
| `read_run_csv(path, columns=None)` | pandas-reads run.csv into a DataFrame in **SI units** (auto-drops unreliable columns; pass `columns` for big files) |
| `si_scale(col)` / `summarize(df)` | column name → SI factor; quick stats |
| Constants | `OUTPUTS_CORE/EXTRA` (WRT channel set), `TRUTH_ONLY_PREFIXES` (ground-truth prefixes), `UNRELIABLE_COLS` (banned columns) |

Command line (straight-cruise example with run + read-back):

```
python scripts/carsim_batch.py --prog <PROG> --datadir <DATADIR> \
    --base <base.par> --out <scenario dir> --tstop 65 \
    --speed-profile "0:50,65:50" --steer-profile "0:0,65:0" --run --read
```

**Before changing templates / adding channels / extending the script, read `references/python-interface.md`** (rationale for every override keyword, simfile field table, unit contract, failure triage).

Companion `scripts/dump_dll_exports.py`: `python dump_dll_exports.py <any.dll>` lists all export symbols (zero-dependency PE parsing).

---

## 5. Output channels and units (verified against solver output)

### 5.1 Recommended WRT whitelist

```
Vx Vy Ax Ay AVz                       ! cg longitudinal/lateral speed, accelerations, yaw rate
Steer_L1 Steer_R1 Steer_L2 Steer_R2   ! road-wheel angles (not steering wheel angle)
AVy_L1 AVy_R1 AVy_L2 AVy_R2           ! four wheel spin speeds
My_Dr_L1 My_Dr_R1 My_Dr_L2 My_Dr_R2   ! drive/regen torques (regen negative)
My_Bk_L1 My_Bk_R1 My_Bk_L2 My_Bk_R2   ! friction brake torques
Fx_L1 Fx_R1 Fx_L2 Fx_R2               ! tire longitudinal forces (truth - evaluation only!)
Fy_L1 Fy_R1 Fy_L2 Fy_R2               ! tire lateral forces (truth)
Fz_L1 Fz_R1 Fz_L2 Fz_R2               ! vertical loads (truth)
Kappa_L1 ... Alpha_L1 ...             ! slip ratios / slip angles (truth)
ROLL PITCH                            ! sprung roll/pitch (CSV columns are Roll/Pitch, capitalized)
AV_Mt_D1_L AV_Mt_D1_R AV_Mt_D2_L AV_Mt_D2_R   ! four motor speeds
```

Useful columns already in the base: `Xo Yo Yaw Station Throttle SocBttry`, etc. **The `Lat_Veh`/`Lat_Targ` columns are unreliable (verified drift artifacts, up to 15 m) — derive lateral position from `Yo/Yaw` instead.** **Slip-ratio quirk**: `Kappa_*` samples near t≈0 after a standing start show a normalization spike (v≈0 in the denominator), identical regardless of friction — exclude t < 0.5 s when comparing slip levels.

### 5.2 Unit table (measured from CSV; SI factors are built into read_run_csv)

| Channel | Native unit | → SI |
|---|---|---|
| Time | s | — |
| Vx, Vy | km/h | ÷3.6 |
| Ax, Ay | **g** | ×9.81 |
| AVz | deg/s | ×π/180 |
| Steer_* / Steer_SW / Roll / Pitch / Yaw / Alpha_* | deg | ×π/180 |
| AVy_* (wheel speed) | **rpm** | ×2π/60 |
| My_* / F*_* | N·m / N | — |

Sign conventions (verified): left turn → AVz > 0; My_Dr positive = drive, negative = regen; My_Bk non-positive while moving forward. Wheel corners: `L1=FL, R1=FR, L2=RL, R2=RR`.

### 5.3 Scenario-control syntax cheat sheet (for overrides)

```
! Load / inertia / tire-radius parameterization (load-condition scenarios)
M_SU <kg>        IZZ_SU <kg·m²>     LX_CG_SU <m>     H_CG <m>
RRE(axle,side) <mm>  R0(axle,side) <mm>     ! 1,1=FL 1,2=FR 2,1=RL 2,2=RR
```

---

## 6. New vehicle / database exploration

The database is all plain-text .par files; grep covers all exploration (no MCP needed). For detailed commands and flows read **`references/database-exploration.md`**:

- Find datasets by name: `grep -r -i "keyword" <DATADIR>/Vehicles/Assembly --include=*.par -l`; identity lives in the `#FullDataName` line;
- Assembly tree: recursively follow `PARSFILE` lines; datasets actually used by a given run are listed in `run_log.txt`;
- Keyword meaning/units: `run_echo.par` echo → `Help\Memos` manuals → GUI;
- New vehicle: find it → clone a Run Control in the GUI → Run Math Model produces the new base → return to §3.

Dataset-internal syntax (Run Control / Procedure / speed controller / path follower / Segment-Builder road / GUI decoration list) is in **`references/dataset-syntax.md`** — use it only to read files or edit via GUI/MCP; **never** hand-write a thin parsfile for direct solver consumption (Misconception 1).

Recommended convention: **treat the database as read-only**; keep self-built scenario files in your own project directory and reference DB datasets by absolute path.

---

## 7. Pitfall list (all stepped on — do not retry)

1. **Never** feed a thin parsfile referencing a vehicle assembly directly to the solver (Misconception 1); **never** write your own expander (cleaning one error uncovers the next).
2. **Never** import the `_vs` Python extension (vs.py): loading carsim_64.dll as an extension segfaults.
3. **Never** override steering with a closed-loop LTARG_TABLE: same-name tables are **row-appended**, not replaced, and get tangled with the base's table (observed "tracking" a phantom target 14.6 m away). Open-loop `STEER_SW_TABLE` is the only verified steering override.
4. Duplicate abcissa values in a table → parse error; dedupe before generating tables (`carsim_batch._dedupe`).
5. Use forward slashes in CLI command paths; backslash escaping inside Git Bash loops fails silently (symptom: "results didn't change" — check the CSV timestamp first).
6. A GUI-generated simfile may point DLLFILE at the 32-bit DLL → write your own, pinned to 64-bit.
7. License: start `cslm.exe` when headless; for "Unable to load library", check license and DLL path first.
8. `OPT_ALL_WRITE 1` + long scenarios → gigantic ERD; use the WRT whitelist.
9. **If a CarSim MCP is configured**: `set_dataset/set_table/set_link/write_parsfile` write database files directly — when the read-only convention applies, change parameters via override.par only, never via those tools.
10. Whitelist principle: for state estimation / online validation, the estimator sees only the virtual-sensor whitelist; Fx/Fy/Fz/Kappa/Alpha are simulator ground truth — evaluation only, never into the estimator.

---

## 8. VS C API fallback (step-by-step; not pursued, kept as memo)

The DLL exports the full VS C API (list symbols with `scripts/dump_dll_exports.py`). Documented flow (VS_Commands_API memo):

```c
t = vs_setdef_and_read(simfile);   // returns start time
vs_initialize();
dt = vs_get_tstep();
while (!stop) { /* write import arrays / read variables */ t = vs_integrate(t); }   // or vs_integrate_io(t,imp,exp)
vs_terminate_run();  vs_terminate();
```

| Function | Guessed prototype |
|---|---|
| `vs_setdef_and_read` | `double (const char*)` |
| `vs_get_tstep` / `vs_get_time` | `double ()` |
| `vs_get_var_id` / `vs_get_var_ptr` | `int (const char*)` / `double* (int)` |
| `vs_integrate` | `double (double, int*)` (MATLAB docs indicate it returns t and stop) |
| `vs_integrate_io` | `double (double, double*, double*)` |
| `vs_statement` | `int (const char*)` (inject a VS Command after read, before initialize) |
| `vs_error_occurred` / `vs_get_error_message` | `int ()` / `int (char*, int)` |

If you truly need stepping: use a §3.2 simfile as input, a GUI-expanded base, confirm GUI/CSLM is running, and validate return-value semantics on a minimal scenario first. Read variables directly via `vs_get_var_id + vs_get_var_ptr` (no ERD dependency). Load with `ctypes.WinDLL(dll, winmode=0, use_last_error=True)`; stdcall/cdecl share an ABI on 64-bit Windows.

---

## 9. CarSim MCP (optional accelerator — not a dependency)

This skill does not depend on the MCP. If the target machine happens to have a CarSim MCP server configured, it can accelerate exploration: `find_dataset`/`browse_library` (dataset search), `resolve_assembly` (assembly tree), `get_dataset` (structured read), `describe_keyword` (keyword units; run `build_keyword_dictionary` once), `run_solver` (internally the same §3.3 CLI), `read_results` (truncates large outputs — direct CSV reading is better). See references/database-exploration.md §6 for the mapping and the write-tool warning. The run/read main path always goes through the §4 scripts.

---

## 10. Database quick reference

| Location | Contents |
|---|---|
| `Vehicles\Assembly\` | vehicle assemblies (entry point for picking a car; e.g. the B-Class Hbk "EV AWD/4Mot" four-motor EV) |
| `Vehicles\Sprung_Mass\` | sprung-mass parameters (M_SU / LX_CG_SU / H_CG / IZZ_SU) |
| `Powertrain\4wd\` | AWD powertrains (EV twin-motor differentials, battery, motor torque maps) |
| `Runs\` | Run Controls (thin: camera + vehicle + procedure, three PARSFILE lines; their GUI expansion Results\Run_<uuid>\Run_all.par is the base source) |
| `Procedures\` | procedures (constant speed / EPA schedule / EV accel-regen templates) |
| `Control\Speed_t\`, `Control\Driver\`, `Control\Braking\` | speed schedules / driver models / braking datasets |
| `Roads\3D_Road\`, `Roads\XY_Table\`, `Roads\Friction\` | parametric roads / XY polyline roads / friction |
| `IO_Channels\I_Channels\` | import channels (e.g. "EV Wheel Motors Command (4WD)" per-wheel torque injection) |

Dataset IDs (UUID suffixes) differ per install/version/clone — **locate by name, never hardcode**.

---

## 11. Fixed conventions (general items — do not change)

- Body frame: x forward / y left / z up; yaw rate r > 0 = left turn.
- Wheel corners FL, FR, RL, RR (= CarSim L1, R1, L2, R2).
- One directory per scenario (override.par / simfile.sim / run.csv / run_echo.par / run_log.txt, ~10 files); batch runs never overwrite each other.
- Truth isolation: the estimator sees only whitelisted virtual measurements; tire forces / slips / slip angles and other ground truth go to the evaluator only.
