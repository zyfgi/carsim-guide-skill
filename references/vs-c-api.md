# VS C API fallback (step-by-step integration via ctypes)

Use the VS C API only when a program requires direct step-by-step interaction
with the VehicleSim solver and Simulink co-simulation is not the desired
integration route.

For predefined inputs, use the CLI scenario runner. For Simulink-based runtime
feedback, use the verified Simulink route in `references/simulink-cosim.md`.

Status: **documented prototype, not verified end-to-end** — the prototypes below come from the VS_Commands_API memo and MATLAB-facing docs. Validate return-value semantics on a minimal scenario before relying on them.

## Loading

```python
import ctypes
dll = ctypes.WinDLL(r"<PROG>\Programs\solvers\carsim_64.dll",
                    winmode=0, use_last_error=True)
```

Dependent DLLs (road_64.dll, tire_64.dll, maux_64.dll, …) sit in the same directory and resolve automatically. On 64-bit Windows stdcall and cdecl share an ABI, so `WinDLL` vs `CDLL` is low-risk. The solver still needs a license (GUI or cslm.exe running).

List all exported symbols (300+) with the bundled tool:

```
python scripts/dump_dll_exports.py "<PROG>\Programs\solvers\carsim_64.dll"
```

## Documented flow (VS_Commands_API memo, simple_loop / path_follower)

```c
t = vs_setdef_and_read(simfile);   // build model + read all inputs; returns start time
vs_initialize();                   // compute initial conditions
dt = vs_get_tstep();
while (!stop) { /* write import arrays / read variables */ t = vs_integrate(t); }
                                   // or vs_integrate_io(t, imp_ptr, exp_ptr)
vs_terminate_run();                // write end files, clean up
vs_terminate();                    // release the model
```

## Function prototypes (confirm before production use)

| Function | Guessed prototype | Notes |
|---|---|---|
| `vs_setdef_and_read` | `double (const char*)` | arg = simfile or parsfile; returns start time |
| `vs_initialize` | `void ()` | |
| `vs_get_tstep` / `vs_get_time` | `double ()` | integration step / current time |
| `vs_get_var_id` | `int (const char*)` | name → id, −1 if unknown |
| `vs_get_var_ptr` | `double* (int)` | id → memory pointer; ctypes reads it directly (per-step sampling without ERD) |
| `vs_integrate` | `double (double, int*)` | MATLAB docs indicate it returns (t, stop) |
| `vs_integrate_io` | `double (double, double*, double*)` | step with import/export arrays |
| `vs_statement` | `int (const char*)` | inject one VS Command after read, before initialize (EQ_OUT/IMPORT/OUTPUT …) |
| `vs_error_occurred` | `int ()` | 0 = OK |
| `vs_get_error_message` | `int (char*, int)` | error text |
| `vs_terminate_run` / `vs_terminate` | `void ()` | end / release |
| `vs_run` | `int (const char*)` | whole-run (smoke-test comparison) |
| `vs_set_stop_run` | `void ()` | request early termination |

## If you go this route

1. Use a simfile backed by a GUI-expanded base (CSV outputs off when values are read through `vs_get_var_ptr`).
2. Confirm GUI/CSLM is running (license).
3. Validate on a minimal scenario first: check `vs_error_occurred()` after every stage, print `vs_get_output_message` / `vs_get_error_message` buffers, and compare one stepped trajectory against a `vs_run` of the same simfile.
4. Import semantics: import values are held over [k, k+1) (zero-order hold) — verify with wheel-speed increments before trusting closed-loop timing.
