# Compatibility

## Verified environment

- CarSim 2024.0 on Windows 10/11 x64.
- 64-bit `VS_SolverWrapper_CLI_64.exe` with `carsim_64.dll`.
- Headless CLI scenarios and isolated batch runs.
- Named, SHA256-bound GUI-expanded Run Control bases.
- Native CSV output with registered SI conversions.
- Registered sprung-body scalar overrides.
- Structured `SPEED_TARGET_TABLE` overrides with solver, echo, and result
  confirmation.
- MATLAB R2025b with Simulink 25.2 for the supplied co-simulation path.

## Other CarSim versions

Standard installation names are detected automatically. A version that is not
listed as verified follows the generic compatible path and is recorded with an
unverified warning. Successful version detection or file parsing does not
establish solver compatibility; confirm the generated files and a complete
local run.

## Capability boundaries

- Generic scalar overrides require confirmed keyword meaning and native unit.
- Table syntax and replacement behavior can vary by keyword and table family.
- Dataset-reference syntax depends on the accepting keyword and dataset
  family. Exact dataset-name resolution does not prove compatibility.
- The low-level VS API route is intended for advanced integrations and needs
  target-specific validation.
- Original DATADIR content remains read-only; use overrides or explicitly
  cloned GUI datasets.
