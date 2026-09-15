# CarSim Guide

An [Agent Skills](https://agentskills.io) skill for configuring, running, and
inspecting CarSim through deterministic Python, CLI, and Simulink workflows.

## What this skill does

- Discovers CarSim installation paths and validates the 64-bit solver.
- Runs scenarios headlessly from Python or validated YAML after one-time base
  expansion and binding.
- Binds GUI-expanded Run Control bases by name and SHA256.
- Applies typed vehicle, scalar, table, and dataset-reference overrides.
- Discovers unknown outputs and parameters without guessing identifiers.
- Runs isolated parameter sweeps with per-run manifests.
- Reads native result CSV files with verified SI conversions.
- Routes real-time feedback tasks to Simulink or the VS API.
- Diagnoses environment, license, compilation, solver, output, and echo errors.

## Why this skill?

CarSim already provides its GUI, solver, database, command-line interface,
MATLAB/Simulink integration, and VehicleSim interfaces. This skill adds an
agent-safe orchestration layer for evidence-based discovery, validated
scenarios and deterministic overrides, repeatable execution, effective-result
validation, control-mode routing, and run provenance through manifests. It is
self-contained around deterministic scripts and does not require an MCP
server.

## Requirements

- Windows x64 with CarSim and a valid solver license.
- Python 3.8+.
- Packages in `requirements.txt`.
- MATLAB and Simulink only for co-simulation workflows.

Install Python dependencies with:

```text
python -m pip install -r requirements.txt
```

## Installation

Clone the repository into a personal or project skill directory:

```text
git clone https://github.com/zyfgi/carsim-guide-skill ~/.agents/skills/carsim-guide
git clone https://github.com/zyfgi/carsim-guide-skill .agents/skills/carsim-guide
```

For Claude Code, use `~/.claude/skills/carsim-guide`. On Windows, cloning to a
normal folder and creating a directory link into the agent's skill directory
also works.

## Quick start

1. Install the requirements:

   ```text
   python -m pip install -r requirements.txt
   ```

2. Discover and cache the local CarSim paths:

   ```text
   python scripts/setup_paths.py
   ```

3. In CarSim, generate a GUI-expanded `Run_all.par` from the intended Run
   Control once. The skill intentionally uses this trusted base instead of
   reimplementing CarSim's complete Run Control expansion and internal dataset
   resolution.

4. Bind the base by name and SHA256:

   ```text
   python scripts/base_registry.py --registry bases.local.json \
     --name distributed_ev --base C:/work/Run_all.par \
     --version 2024.0 --run-control <id> --vehicle <name>
   ```

5. Run the basic scenario:

   ```text
   python scripts/scenario_runner.py examples/scenarios/basic_cruise.yaml \
     --registry bases.local.json --out runs --run
   ```

6. Inspect `runs/basic_cruise/run.csv`, `run_echo.par`, and
   `run_manifest.json`. For failures, use `scripts/diagnose_run.py` and
   `references/troubleshooting.md`.

Here, headless means solver execution after the one-time GUI expansion and
base binding. Different vehicles, procedures, drivers, controls, or other
incompatible execution contexts may require separate bound bases.

## Core capabilities

| Task | Primary entry point |
|---|---|
| Installation/path discovery | `scripts/setup_paths.py` |
| Direct Python/CLI scenario | `scripts/carsim_batch.py` |
| YAML scenario and manifest | `scripts/scenario_runner.py` |
| Named base binding | `scripts/base_registry.py` |
| Parameter overrides | `scripts/parameters.py` |
| Output discovery and units | `scripts/output_registry.py` |
| Parameter discovery | `scripts/parameter_discovery.py` |
| Dataset inspection | `scripts/database_tools.py` |
| Batch sweeps | `scripts/batch_runner.py` |
| Run diagnostics | `scripts/diagnose_run.py` |
| Simulink co-simulation | `examples/simulink_cosim.py` |
| Torque vectoring | `examples/torque_vectoring.py` |

`SKILL.md` is the agent router. Detailed procedures are loaded on demand from
`references/`.

## Example workflows

### Steering and tire outputs

Start with the YAML files under `examples/scenarios/` for straight cruise,
friction changes, steering maneuvers, tire-force output, and vehicle
overrides.

### Friction or parameter sweep

Use the formal batch runner rather than writing separate scenarios manually:

```text
python scripts/batch_runner.py examples/batches/friction_sweep.yaml \
  --registry bases.local.json --out runs --run
```

The batch runner delegates each member to `scenario_runner.py`, isolates
failures, and writes one batch manifest.

### Closed-loop control

Use `examples/simulink_cosim.py` for runtime feedback through the CarSim
S-Function. Use `examples/torque_vectoring.py` for four-wheel motor-torque
control. Prerecorded tables and batch replay are not closed-loop control.

### Discovery

The scripts under `examples/discovery/` demonstrate evidence-based output,
parameter, and dataset dependency discovery.

## Reproducing a run on another machine

Absolute installation paths in a manifest are machine provenance, not
portable identity. To reproduce a run, use the same compatible CarSim version,
bind an equivalent GUI-expanded base and verify its SHA256, reuse the saved
scenario, then compare the new manifest and `run_echo.par`. The version, base
hash, exact scenario, `scenario_sha256`, and critical input hashes provide the
portable identity; bit-for-bit equality across machines is not assumed.

## Safety and database policy

- Keep the original CarSim DATADIR read-only.
- Apply changes through scenario overrides or an explicitly cloned GUI
  dataset.
- Never select the newest `Run_all.par`; bind the intended execution context
  by name and SHA256.
- Do not infer CarSim channel names, parameter keywords, or native units from
  natural-language descriptions.
- External dataset references are recorded but not opened unless external
  traversal is explicitly enabled.
- Accept results only after fresh-artifact, normal termination, required
  channel, finite time-grid, and applicable echo checks.

## Compatibility

The verified environment and version-specific limitations are summarized in
[`references/compatibility.md`](references/compatibility.md). Version parsing
and warning behavior are described in
[`references/version-compatibility.md`](references/version-compatibility.md).

CarSim 2024.0 on Windows x64 is the verified solver target. Other detected
versions use the generic path with an unverified warning and still require
local solver acceptance.

## Limitations

- A GUI-expanded Run Control base is required; a thin hand-written dataset
  tree is not a substitute.
- Generic parameter and table overrides require confirmed keyword semantics,
  native units, and context.
- Dataset-reference compatibility depends on the target keyword and dataset
  family; successful name resolution alone is insufficient.
- Low-level VS API stepping is available as an advanced route but requires
  application-specific integration and validation.
- `Lat_Veh` and `Lat_Targ` are excluded because they are known drift
  artifacts; use `Yo`/`Yaw` for lateral position.

## License

MIT — see [LICENSE](LICENSE).
