# CarSim Guide

An [Agent Skills](https://agentskills.io) skill for configuring, running, and
inspecting CarSim through deterministic Python, CLI, and Simulink workflows.

## What this skill does

- Discovers CarSim installation paths and validates the 64-bit solver.
- Runs headless scenarios from Python or validated YAML.
- Binds GUI-expanded Run Control bases by name and SHA256.
- Applies typed vehicle, scalar, table, and dataset-reference overrides.
- Discovers unknown outputs and parameters without guessing identifiers.
- Runs isolated parameter sweeps with per-run manifests.
- Reads native result CSV files with verified SI conversions.
- Routes real-time feedback tasks to Simulink or the VS API.
- Diagnoses environment, license, compilation, solver, output, and echo errors.

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

Run path discovery once after installation:

```text
python scripts/setup_paths.py
```

This validates the CarSim program directory, DATADIR, CLI solver, and 64-bit
DLL, then caches the selected paths for later sessions.

## Basic usage

A base is a GUI-expanded CarSim Run Control / execution context. Different
vehicles, procedures, drivers, controls, or other incompatible run
configurations may require separate bases.

Bind a base explicitly:

```text
python scripts/base_registry.py --registry bases.local.json \
  --name distributed_ev --base C:/work/Run_all.par \
  --version 2024.0 --run-control <id> --vehicle <name>
```

Compile or run a YAML scenario:

```text
python scripts/scenario_runner.py examples/scenarios/basic_cruise.yaml \
  --registry bases.local.json --out runs

python scripts/scenario_runner.py examples/scenarios/basic_cruise.yaml \
  --registry bases.local.json --out runs --run
```

Each run gets an immutable directory containing the scenario snapshot,
`override.par`, `simfile.sim`, result files, and `run_manifest.json`.

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
