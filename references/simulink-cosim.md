# Simulink Co-simulation (verified recipe)

How to run CarSim coupled with a Simulink controller, entirely from scripts (no GUI model editing). Verified end-to-end: a PI yaw-rate tracker steering a 4-motor EV via `vs_sf`, 1 kHz exchange, **0.00% steady-state tracking error**; also confirmed working on MATLAB **R2025b** + CarSim 2024.0 (newer than the officially supported range — R2023a+ required by the tooling, older CarSim-verified combos top out around R2023b/R2024a).

For identification/data loops without MATLAB, prefer the CSV batch workflow (SKILL.md §3-§4) — 16×+ faster and dependency-free. Use Simulink when the controller/algorithm lives in Simulink.

## 1. Mechanism

```
Simulink model (your controller)
  import array -> [vs_sf S-Function] -> export array
                    | reads simfile.sim (PORTS_IMP/PORTS_EXP > 0)
                    v
              VS solver steps at EXT_MODEL_STEP
```

- The solver ships as `vs_sf.mexw64` inside `<PROG>\Programs\solvers\Matlab\`, wrapped by the library `Solver_SF.slx` (same folder; `slblocks.m` registers it as the "VehicleSim" library).
- Import/export declarations live in the parsfile; the counts live in BOTH the parsfile and the simfile (see pitfall 1).
- Exports carry **native CarSim units** (km/h, deg/s, g) — convert where you consume them.

## 2. Verified recipe (programmatic, no GUI)

1. **Generate the co-sim inputs with the normal override workflow**, adding import/export declarations via `unsafe_extra_lines` (see `examples/simulink_cosim.py`):

   ```
   IMPORT IMP_STEER_SW REPLACE      ! steering wheel angle [deg] from Simulink
   EXPORT Vx                         ! export order = declaration order
   EXPORT AVz                        ! [deg/s]
   EXPORT Ay                         ! [g]
   EXPORT Yo                         ! [m]
   EXPORT Steer_SW                   ! [deg]
   PORTS_IMP 1,1                     ! <array #>,<count>  -- NOT a single count!
   PORTS_EXP 1,5
   ```

   and patch the simfile the same way: `PORTS_IMP 1,1`, `PORTS_EXP 1,5`. Keep `EXT_MODEL_STEP` = solver `TSTEP`.

2. **Build and run the model headless** (`scripts/cosim_model.m`):

   ```
   matlab -batch "addpath('<PROG>\Programs\solvers\Matlab'); cosim_model('<workdir>')"
   ```

   The script builds a model with the `Solver_SF/CarSim S-Function` library block (`SIMFILE` mask parameter = `simfile.sim`, resolved from the model's working directory), a PI controller on the exported yaw rate, saturation, and To Workspace sinks; runs it fixed-step at the exchange rate; and writes `cosim_results.csv`.

3. **Verify in Python**: read `cosim_results.csv` with pandas, convert native units to SI.

## 3. Pitfalls (all stepped on — do not retry)

1. **PORTS syntax is two numbers**: `PORTS_IMP <array#>,<count>` (e.g. `PORTS_EXP 1,5`). A single number is parsed as the *array number* — `PORTS_EXP 5` produces the baffling error `S-function 'vs_sf' ... output port 5 has an invalid width`.
2. **Use the library block, not a raw S-Function block**: `Solver_SF/CarSim S-Function` with mask parameter `SIMFILE`. A raw S-Function block whose `Parameters` is `simfile.sim` fails compilation — Simulink evaluates the string as a MATLAB expression (`unable to resolve name`).
3. **Import activation**: `IMPORT IMP_STEER_SW REPLACE` is the proven-active form (matches official runs with live ports). The `VS_ADD 0` form parsed fine but the signal stayed inert in testing — don't waste an hour on it.
4. **To Workspace time is already numeric** — never wrap it in `seconds()` (it converts doubles *into* durations and corrupts the whole exported matrix; symptom: every CSV field suffixed like `4.32e+06`).
5. **Discrete-Time Integrator has no `Gain` parameter** (name differs across releases) — use gain 1 in the block and a plain Gain block after it.
6. **License still applies** (GUI or `cslm.exe`), same as the headless CLI.
7. Fixed-step solver (`ode1`) with `FixedStep` = `EXT_MODEL_STEP` = solver `TSTEP`.

## 4. Reference demo numbers (your acceptance yardstick)

PI yaw-rate target 0.15 rad/s at 50 km/h cruise: steady error 0.00%, 95% rise 0.09 s, overshoot 13%, plant gain ≈ 0.26-0.28 (deg/s yaw)/deg SW — the same gain an independent Python closed-loop calibration measured (0.13% error in 3 runs), which cross-validates both paths.

## 5. Related tooling

- **Simulink Agentic Toolkit** (github.com/matlab/simulink-agentic-toolkit): official MathWorks skills giving agents Model-Based-Design knowledge for building/editing/testing Simulink models — pairs well with this skill (we generate the CarSim side, it builds the controller side). NOT required for the recipe above (plain `matlab -batch` suffices); install it for nontrivial model-design work:

  ```bash
  git clone --depth 1 https://github.com/matlab/simulink-agentic-toolkit /tmp/satk
  cp -r /tmp/satk/skills-catalog/{simulink-modeling,simulink-simulation,simulink-environment-fundamentals,control-systems} ~/.agents/skills/
  ```

  (adjust the target to your agent's skills directory; MathWorks license applies — use in conjunction with MathWorks products.)
- Component-level S-Functions (`vs_dyn`, `vs_kin`, `vs_ctl`, `vs_state` in the same folder) expose sub-models separately; UDP blocks exist for distributed setups.


## Research-contract integration update

The Python examples now create a single `SimulationConfig` and pass its duration
and dt to both CarSim files and the MATLAB model builder. MATLAB builders accept
optional `tstop, dt` arguments; their integrators and fixed-step solver use the
same dt. Examples keep the verified 1 ms default.

`PROGDIR` and `DATADIR` must include their trailing path separator. Some native
terrain references concatenate the directory string with a filename; omitting
it caused `...DataProving_Ground.vsterrain` and a stop at t=0 in a regression run.
The generator now preserves the separator and disables error dialogs before
reading the base. Python captures both MATLAB stdout and stderr in
`matlab_output.txt` so startup and solver errors are reviewable.
