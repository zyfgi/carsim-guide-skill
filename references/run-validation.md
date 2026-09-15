# Run validation (core)

Two complementary layers, both core capabilities. Neither invents physics
adequacy: they prove the run executed as configured.

## Compile-time checks (before the solver)

`scenario_runner.verify_compiled` inspects the generated files and reports
structured errors: `TSTEP` (override.par) must equal `EXT_MODEL_STEP`
(simfile.sim); `DLLFILE` must pin the 64-bit solver; `PRODUCT_VER` must match
the pinned base version; the `WRT_` output list must be non-empty; the base
snapshot hash must still match the registry binding.

## Post-run checks

`validate_run.check_run(...) -> RunValidationResult(passed, issues, metrics)`
never raises. Issues carry `severity` (error / warning), a stable `code` and a
message:

- **errors** (fail the run): missing/empty `run.csv` or `run_echo.par`, stale
  artifacts (mtime before run start), missing requested channels, non-numeric
  or NaN/inf values, wrong sample count, time grid not strictly increasing on
  the requested dt through TSTOP, echo parameter absent or mismatched,
  movement threshold not met (when configured), solver stdout lacking
  `Termination at simulation time`.
- **warnings** (pass with a note): `run_log.txt` absent (dataset provenance
  not recorded).

`metrics` reports samples, final time, echoed parameter values and the
movement threshold. `validate_run(...)` is the compatibility wrapper: it
raises `ValueError` on the first error and returns the legacy metrics dict.

Echo validation uses exact `KEYWORD value` matches in `run_echo.par`
(rel 1e-6). It covers scalar keywords that echo line-by-line; keywords that
cannot be reliably extracted are reported as absent rather than assumed OK.
For table overrides, inspect the complete echoed table block and confirm the
result behavior. `SPEED_TARGET_TABLE` is a verified structured path; other
table families require confirmation in the target Run Control.

```python
from validate_run import check_run
result = check_run(run_dir, simulation, ["Vx", "AVz"], started_at=t0,
                   expected_parameters={"M_SU": 1250.0},
                   minimum_speed_mps=1.0, solver_stdout=stdout)
if not result.passed:
    for issue in result.errors():
        print(issue.code, issue.message)
```
