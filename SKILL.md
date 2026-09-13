---
name: carsim-guide
description: CarSim 2024.0 (VS Solver) runtime mechanics and headless scripting guide. Covers the override.par pattern (GUI-expanded base + keyword overrides), a self-contained simfile template, CLI batch runs, Python interface scripts (generate / run / read CSV), output channels and unit conversion, database exploration, Simulink co-simulation via the vs_sf S-Function, and a field-tested pitfall list. Self-contained - no CarSim MCP required. Use when dealing with CarSim headless runs, VS solver CLI, simfile.sim / Run_all.par / override.par workflows, ERD/CSV result reading, vehicle / procedure / road dataset changes, or Simulink+CarSim co-simulation - even if the user never mentions the runtime mechanics.
---

# CarSim 2024.0 Runtime Mechanics & Operation Guide (agent reference, field-verified)

Updated 2026-09-13. Everything marked "verified" was validated by actually running it (multi-scenario batch runs, RTIME≈0.05; performance varies by machine). Self-contained: no MCP, no Simulink, no VS C API. Paths are placeholders — resolve on the target machine.

**Companion files (read on demand, not upfront):**
- `scripts/carsim_batch.py` — full workflow: generate override.par/simfile, run headless, read CSV (CLI + library)
- `scripts/cosim_model.m` — Simulink co-sim model builder (PI demo, run via matlab -batch)
- `scripts/dump_dll_exports.py` — zero-dependency DLL export-symbol enumerator
- `examples/param_sweep.py` — runnable batch parameter-sweep example
- `examples/simulink_cosim.py` — runnable Simulink+CarSim closed-loop demo (end to end)
- `references/python-interface.md` — before modifying/extending the script: keyword rationale, simfile fields, unit contract, failure triage
- `references/database-exploration.md` — finding vehicles / assembly trees / keyword units (grep recipes, no MCP)
- `references/dataset-syntax.md` — .par dataset syntax templates
- `references/simulink-cosim.md` — Simulink co-simulation via vs_sf: verified recipe + pitfalls (PORTS syntax, import activation, R2025b)
- `references/vs-c-api.md` — VS C API (ctypes) stepping fallback, only if hard-real-time coupling is required
- `evals/evals.json` — trigger/behavior tests for this skill

---

## 0. Quick start (fresh machine → first successful run)

1. **Locate the install**: `<PROG> = …\CarSim2024.0_Prog`, `<DATADIR> = …\CarSim2024.0_Data` (siblings).
2. **License**: keep the CarSim GUI open, or start `<PROG>\Programs\cslm.exe`.
3. **Get a base (once per vehicle — the ONLY GUI step)**: open a Run Control → **Run Math Model** → take `Results\Run_<uuid>\Run_all.par`.
4. **First run** (65 s straight cruise at 50 km/h):
   ```
   python scripts/carsim_batch.py --prog <PROG> --datadir <DATADIR> \
       --base <Run_all.par> --out <scenario dir> \
       --tstop 65 --speed-profile "0:50,65:50" --run --read
   ```
5. **Acceptance**: stdout ends with `Termination at simulation time = 65 s`; `<out>/run.csv` exists (1 kHz CSV).

Daily runs end here — no GUI, no database writes, no Simulink, no C API.

---

## 1. Key paths (placeholders — resolve on the target machine)

| Item | Path / value |
|---|---|
| Program root PROG | `<CarSim install root>\CarSim2024.0_Prog` |
| Database DATADIR (read-only) | `<CarSim install root>\CarSim2024.0_Data` |
| CLI solver wrapper | `<PROG>\Programs\VS_SolverWrapper_CLI_64.exe` |
| Solver DLL (64-bit) | `<PROG>\Programs\solvers\carsim_64.dll` (full VS C API, 300+ symbols) |
| License | GUI running, or `Programs\cslm.exe` headless |
| Manuals | `Help\Memos\*.pdf`, `Help\Manuals\VS_SDK.pdf` |
| Python | bring your own 3.x with pandas; CarSim's bundled Python (no pip) is unused |

**Pitfall**: the official `Programs\Python\vs.py` / `_vs` extension **segfaults** on import — never use it.

---

## 2. Overall run model (two falsified misconceptions)

The GUI's Run does two things: ① expands database datasets into Run_all.par, ② calls the solver DLL. The CLI wrapper only does ②.

- **Misconception 1 (falsified)** — the solver cannot recursively parse raw database .par files (GUI-only decorations; deterministic segfault at the hanging-damper dataset). It only accepts GUI-expanded content. Correct loop: one GUI base per vehicle, then override everything. Do not hand-write thin parsfiles; do not write your own expander.
- **Misconception 2 (demoted)** — online validation does NOT require VS C API stepping. A 1 kHz CSV batch + causal replay by arrival time satisfies the "only arrived observations" constraint and is 16×+ faster.

Data flow: `simfile.sim` → `INPUT` parsfile (base + overrides) → parse → integrate → `ERDFILE` CSV.

---

## 3. The override.par pattern (core mechanism, verified)

CarSim parses parsfiles **last-write-wins**: reference the base first, then every keyword/table after it overrides the base. Override skeleton (full annotated template + rationale: `references/python-interface.md` §1; the script generates it):

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

**simfile** (§3.2, self-contained — all output paths into the scenario dir): `FILEBASE/INPUT/INPUTARCHIVE/ECHO/FINAL/LOGFILE/ERDFILE` + `PROGDIR/DATADIR/PRODUCT_ID CarSim/PRODUCT_VER 2024.0/VEHICLE_CODE i_i/EXT_MODEL_STEP/PORTS_IMP 0/PORTS_EXP 0/DLLFILE …\carsim_64.dll` (**always pin 64-bit**; GUI-generated files may say 32-bit) + `END`. Exact template: `carsim_batch.simfile()`.

**Run** (§3.3): `"<PROG>\Programs\VS_SolverWrapper_CLI_64.exe" -sim <simfile>`. Success = stdout `Termination at simulation time = <TSTOP>` (RTIME lands in run_log.txt / run_end.par). Use forward slashes on the command line — backslash escaping in Git Bash fails silently.

**Other CLI flags** (§3.4): `-par <expanded parsfile>`, `-uuid <Run uuid>`, `<simfile> -rundoc -imptxt -outtxt` (docs only; `-gen_run_all` does not work).

---

## 4. Python tooling (scripts/carsim_batch.py)

| API | Purpose |
|---|---|
| `make_scenario(out_dir, base_run_all, prog, datadir, tstop, speed_rows, steer_rows, mu=0.9, extra_lines=())` | writes override.par + simfile.sim, returns simfile path; `extra_lines` injects parameter overrides (static payloads) |
| `run_solver(simfile_path, prog, timeout=600)` | subprocess CLI call (argv list + forward slashes), success-judged, raises with output tail |
| `read_run_csv(path, columns=None)` | pandas → **SI-unit** DataFrame (auto-drops unreliable columns, respects requested order) |
| `si_scale(col)` / `summarize(df)` / constants | column→SI factor; stats; `OUTPUTS_*`, `TRUTH_ONLY_PREFIXES`, `UNRELIABLE_COLS` |

CLI: `--prog --datadir --base --out --tstop --speed-profile "t:v,…" --steer-profile "t:v,…" --mu --run --read --verbose`. See `examples/param_sweep.py` for a runnable batch sweep.

---

## 5. Output channels and units (verified)

Recommended WRT set (`OUTPUTS_CORE/EXTRA` in the script): cg states (`Vx Vy Ax Ay AVz`), road-wheel steer + wheel speeds + drive/brake torques per corner (`Steer_/AVy_/My_Dr_/My_Bk_{L1,R1,L2,R2}`), tire truths (`Fx_/Fy_/Fz_/Kappa_/Alpha_`), `ROLL PITCH`, motor speeds `AV_Mt_D1_*/D2_*`. Useful base columns: `Xo Yo Yaw Station Throttle SocBttry`.

**Unreliable**: `Lat_Veh`/`Lat_Targ` drift (up to 15 m) — lateral position from `Yo/Yaw`. **Slip quirk**: `Kappa_*` has a t≈0 normalization spike after a standing start (identical regardless of friction) — exclude t < 0.5 s when comparing slip.

Units → SI (built into `read_run_csv`): Vx/Vy km/h÷3.6; Ax/Ay **g**×9.81; AVz/angles deg×π/180; AVy_* **rpm**×2π/60; forces/torques already SI. Signs (verified): left turn → AVz>0; My_Dr + = drive, − = regen; My_Bk ≤ 0 forward. Corners: L1=FL, R1=FR, L2=RL, R2=RR.

**Parameter overrides** (§5.3, inject via `extra_lines`): `M_SU <kg>`, `IZZ_SU <kg·m²>`, `LX_CG_SU/H_CG_SU/Y_CG_SU <mm>`, `RRE/R0(axle,side) <mm>`. **Y_CG_SU quirk (A/B/C/D verified)**: static left-right load split is exactly linear in the value but ≈**2.07×** the naive rigid prediction; ground-truth lateral CG = the `Y_CG_TL` (CALC) line in `run_echo.par` — never invert the Fz split naively.

---

## 6. New vehicle / database exploration

The database is plain-text .par; grep covers everything (recipes in `references/database-exploration.md`): find datasets by `#FullDataName`, assembly trees via recursive `PARSFILE` lines, keyword units from `run_echo.par` → manuals → GUI. A run's actually-used datasets are listed in `run_log.txt`. Library map: `Vehicles\Assembly\` (entry), `Vehicles\Sprung_Mass\`, `Powertrain\`, `Procedures\`, `Runs\` (thin Run Controls — the base source), `Control\{Speed_t,Driver,Braking}\`, `Roads\{3D_Road,XY_Table,Friction}\`, `IO_Channels\I_Channels\`. Dataset IDs (UUIDs) differ per install — locate by name, never hardcode.

New vehicle: find it → clone a Run Control in the GUI → Run Math Model → new base → back to §3. Dataset internals for reading/GUI-or-MCP editing: `references/dataset-syntax.md` (never hand-write thin parsfiles — Misconception 1).

**Convention**: treat the database as read-only; keep scenario files in your own directory, referencing DB datasets by absolute path.

---

## 7. Common mistakes (all field-tested — do not retry)

1. Thin parsfile referencing a vehicle assembly → solver segfault; hand-written expanders → whack-a-mole errors. Use the override pattern only.
2. `_vs` Python extension (vs.py) → segfault. Use the CLI / scripts.
3. Closed-loop `LTARG_TABLE` steering override → rows are **appended**, not replaced (phantom target 14.6 m observed). Open-loop `STEER_SW_TABLE` only.
4. Duplicate table abcissa → parse error; dedupe (`carsim_batch._dedupe`).
5. Backslash paths on the Git Bash command line → silent wrong-file runs ("results didn't change" — check the CSV timestamp).
6. GUI-generated simfile DLLFILE may be 32-bit → pin 64-bit.
7. No license → "Unable to load library"; start `cslm.exe` headless.
8. `OPT_ALL_WRITE 1` + long runs → GB-scale ERD; use the WRT whitelist.
9. If a CarSim MCP is present: `set_dataset/set_table/set_link/write_parsfile` write DB files — under the read-only convention use override.par instead.
10. Truth isolation: Fx/Fy/Fz/Kappa/Alpha are simulator ground truth — evaluation only, never into an estimator.

---

## 8. Delegation & fallbacks (when NOT to use this workflow)

- **Base generation & human browsing** → delegate to the VS Browser GUI (once per vehicle; §6).
- **MATLAB / Simulink co-simulation** → supported and field-verified when the controller lives in Simulink: `references/simulink-cosim.md` (PI yaw-tracking demo, 0.00% error; programmatic build via `scripts/cosim_model.m`, runnable driver `examples/simulink_cosim.py`). For identification/data loops, stay with the CSV batch — 16×+ faster and MATLAB-free.
- **Hard real-time stepping** (true closed-loop coupling at solver rate) → only then consider the VS C API via ctypes: see `references/vs-c-api.md` (documented prototypes; unverified end-to-end — prototype only).
- **CarSim MCP server, if configured** → optional exploration accelerator (`find_dataset`, `resolve_assembly`, `get_dataset`, `describe_keyword`); run/read always via the §4 scripts. See `references/database-exploration.md` §6 for the mapping and the write-tool warning.

---

## 9. Fixed conventions (do not change)

- Body frame x forward / y left / z up; yaw rate r > 0 = left turn.
- Corners FL, FR, RL, RR (= L1, R1, L2, R2).
- One directory per scenario (override.par / simfile.sim / run.csv / run_echo.par / run_log.txt, ~10 files); batch runs never overwrite each other.
- Estimator-visible channels = whitelist only; ground-truth channels go to the evaluator.
