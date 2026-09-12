# Python Interface Walkthrough (scripts/carsim_batch.py)

This document walks through the design and evidence behind `scripts/carsim_batch.py`. All conclusions are field-verified (multi-scenario batch runs succeeded, RTIME≈0.05, roughly 17× real time; performance varies by machine).

## 0. Workflow overview

```
base Run_all.par (GUI-expanded base, once per vehicle)
        |  referenced by
        v
override.par (appended overrides: run switches + speed table + friction + open-loop steer + WRT channels)
        |  referenced by INPUT
        v
simfile.sim (self-contained run description, ERDFILE=run.csv)
        |  -sim
        v
VS_SolverWrapper_CLI_64.exe (headless solve; license needs the GUI or cslm.exe running)
        v
run.csv (1 kHz text CSV) --pandas--> SI-unit DataFrame
```

The script wraps this flow into three independently callable functions: `make_scenario()` (steps 1+2), `run_solver()` (3), `read_run_csv()` (4).

## 1. override_par(): why each override exists

CarSim parses parsfiles **last-write-wins**: a keyword written later replaces an earlier one. The first line of override.par is `PARSFILE <absolute base path>`, pulling in the entire expanded base, so every subsequent line naturally takes effect. Rationale per keyword group:

| Keyword | Purpose / pitfall evidence |
|---|---|
| `OPT_ERROR_DIALOG 0` | required headless: an error dialog would hang the process |
| `OPT_ALL_WRITE 0` + `WRT_<channel>` | write only declared channels. `OPT_ALL_WRITE 1` + long scenarios produces GB-scale ERD |
| `OPT_VS_FILETYPE 4` | ERD output as **text CSV** (default 2 is binary .vs, not pandas-readable) |
| `TSTOP` / `OPT_STOP 0` / `SSTOP 100000` | stop by time; disable stop-on-distance |
| `TSTEP 0.001` + `IPRINT 1` | 1 ms step, one row per step → 1 kHz sampling |
| `OPT_SC 1` + `SPEED_TARGET_COMBINE ADD` + `SPEED_TARGET_TABLE` | closed-loop speed controller, target = table (t s, km/h). **Initial speed = first row** |
| `OPT_SC_ENGINE_BRAKING 1` | EV: prefer motor regen while decelerating |
| `MU_ROAD_CARPET 2D_STEP` | friction override (3-column table: s, mu_left, mu_right). If the base is a low-mu scenario, ordinary scenarios **must** override it or the tires saturate early |
| `OPT_DM 0` + `STEER_SW_TABLE` | **open-loop steering is the only reliable steering override**. A closed-loop LTARG_TABLE is row-appended, not replaced (observed "tracking" a phantom target 14.6 m away) — never use it to override |
| `LOG_ENTRY` + `END` | log marker + parsfile terminator (every par needs END) |

The `_table()` helper emits `NAME <interp> … ENDTABLE` blocks; `_dedupe()` drops repeated abcissa values — CarSim rejects duplicate x values inside a table.

## 2. simfile(): field quick reference

| Field | Notes |
|---|---|
| `FILEBASE/INPUT/INPUTARCHIVE/ECHO/FINAL/LOGFILE/ERDFILE` | all absolute paths into the scenario directory → per-scenario isolated output; batch runs never collide. `ECHO` (parse echo) and `LOGFILE` (lists every dataset actually used) are debugging evidence |
| `ERDFILE <dir>/run.csv` | combined with `OPT_VS_FILETYPE 4`, yields a CSV directly |
| `VEHICLE_CODE i_i` | vehicle code (i_i = car-to-car; copy the value matching the base) |
| `EXT_MODEL_STEP` | keep equal to TSTEP |
| `DLLFILE` | **pin 64-bit** carsim_64.dll; GUI-generated simfiles may write 32-bit |

## 3. run_solver(): CLI invocation and success criteria

```python
cmd = [exe, "-sim", simfile_path.replace("\\", "/")]
subprocess.run(cmd, capture_output=True, text=True, timeout=...)
```

- Uses an **argv list** (`shell=False`), which sidesteps shell backslash-escaping entirely; the path is still normalized to forward slashes (the CLI likes those best; typing backslash paths by hand in Git Bash escapes silently — symptom: "results didn't change", check the CSV timestamp).
- **Success criterion**: stdout contains `Termination at simulation time = <TSTOP>`; on failure, raises RuntimeError with the last 40 lines of output.
- Common failures:
  - `Unable to load library` / license error → GUI not open and cslm.exe not running, or a wrong DLLFILE path;
  - "succeeded" but results unchanged → simfile/override path escaping issue; check the simfile path on the first line of run_log.txt.

## 4. read_run_csv(): unit conversion contract (verified)

| CSV column | Native unit | → SI factor |
|---|---|---|
| Time | s | 1 |
| Vx, Vy | km/h | ×0.2777778 |
| Ax, Ay | **g** | ×9.81 |
| AVz | deg/s | ×0.0174533 |
| Roll, Pitch, Yaw, Steer_*, Alpha_* | deg | ×0.0174533 |
| AVy_L1/R1/L2/R2 (wheel speeds) | **rpm** | ×0.1047198 |
| Fx_/Fy_/Fz_ (N), My_Dr_/My_Bk_ (N·m), Kappa_ | SI / dimensionless | 1 |
| AV_Mt_* (motor speeds) | rpm | kept at 1 (multiply by 2π/60 yourself if needed) |

Sign conventions (verified): left turn → AVz > 0; My_Dr positive = drive, negative = regen; My_Bk non-positive while moving forward. Wheel corners `L1=FL, R1=FR, L2=RL, R2=RR`.

**Channel partitioning** (data-isolation principle):
- `TRUTH_ONLY_PREFIXES = (Fx_, Fy_, Fz_, Kappa_, Alpha_)` — simulator ground truth. For state estimation / online validation these channels **must never enter the estimator**; use them only for evaluation;
- `UNRELIABLE_COLS = (Lat_Veh, Lat_Targ)` — verified drift artifacts (up to 15 m); dropped automatically on read; derive lateral position from `Yo/Yaw`.

## 5. Usage examples

Command line (straight cruise, run then read back):

```
python scripts/carsim_batch.py ^
    --prog "C:/CarSim/CarSim2024.0_Prog" --datadir "C:/CarSim/CarSim2024.0_Data" ^
    --base "C:/work/base/Run_all.par" --out "C:/work/S0_straight" ^
    --tstop 65 --speed-profile "0:50,65:50" --run --read
```

(`^` is the Windows cmd line continuation; use `\` in bash.)

As a library (custom lane-change scenario):

```python
from carsim_batch import make_scenario, run_solver, read_run_csv

sim = make_scenario(
    out_dir="C:/work/lane_change",
    base_run_all="C:/work/base/Run_all.par",
    prog="C:/CarSim/CarSim2024.0_Prog",
    datadir="C:/CarSim/CarSim2024.0_Data",
    tstop=300.0,
    speed_rows=[(0, 43), (30, 65), (60, 72), (90, 40), (300, 50)],   # s, km/h
    steer_rows=[(0, 0), (95, 14), (105, 14), (110, -14), (120, -14), (300, 0)],  # s, deg
    mu=0.9,
)
run_solver(sim, prog="C:/CarSim/CarSim2024.0_Prog", timeout=600)
df = read_run_csv("C:/work/lane_change/run.csv", columns=["Time", "Vx", "Ay", "AVz"])
```

Memory note: long scenarios at 1 kHz × 100+ columns can reach hundreds of MB of CSV; `read_run_csv(columns=...)` loads only the needed columns.

## 6. Companion utility

`scripts/dump_dll_exports.py`: zero-dependency PE export-table parser that lists any DLL's export symbols (originally used to confirm that carsim_64.dll exports the full VS C API, 300+ symbols). `python dump_dll_exports.py carsim_64.dll`.
