# Simulink co-simulation

Use CLI batch execution when all external inputs are predefined before the
run. Use Simulink co-simulation when an external controller must affect the
vehicle during the same simulation. The bundled example has been exercised
end-to-end with CarSim 2024.0 and MATLAB R2025b with Simulink 25.2.

## Mechanism

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

## Programmatic route

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

## Runtime requirements

1. **PORTS syntax is two numbers**: `PORTS_IMP <array#>,<count>` (e.g. `PORTS_EXP 1,5`). A single number is parsed as the *array number* and can produce an invalid-width error.
2. **Use the library block, not a raw S-Function block**: `Solver_SF/CarSim S-Function` with mask parameter `SIMFILE`. A raw S-Function block whose `Parameters` is `simfile.sim` fails compilation — Simulink evaluates the string as a MATLAB expression (`unable to resolve name`).
3. **Import activation**: use `IMPORT IMP_STEER_SW REPLACE` for the live steering port. `VS_ADD 0` can parse without activating the signal.
4. **To Workspace time is already numeric** — do not wrap it in `seconds()`, which converts doubles into durations and corrupts the exported matrix.
5. **Discrete-Time Integrator has no `Gain` parameter** (name differs across releases) — use gain 1 in the block and a plain Gain block after it.
6. **License still applies** (GUI or `cslm.exe`), same as the headless CLI.
7. Fixed-step solver (`ode1`) with `FixedStep` = `EXT_MODEL_STEP` = solver `TSTEP`.

## Timing and path consistency

The Python examples create one `SimulationConfig` and pass its duration and
`dt` to both the CarSim files and MATLAB model builder. MATLAB builders accept
optional `tstop, dt` arguments; their integrators and fixed-step solver use the
same `dt`. Keep `EXT_MODEL_STEP`, CarSim `TSTEP`, and the MATLAB fixed step
equal.

`PROGDIR` and `DATADIR` must include their trailing path separator because some
native resources concatenate the directory string with a filename. The
generator preserves the separator and disables error dialogs before reading
the base. Python captures MATLAB stdout and stderr in `matlab_output.txt` so
startup and solver errors are reviewable.
