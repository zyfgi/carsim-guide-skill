> This skill follows the [Agent Skills](https://agentskills.io) standard: a folder with a `SKILL.md` (YAML frontmatter + instructions), bundled scripts, and on-demand references.

# CarSim Guide

A skill for operating CarSim from an AI agent: environment discovery, headless simulation, vehicle/run configuration, parameter overrides, scenario generation, batch runs, output parsing with SI conversion, control inputs (including per-wheel torque), database exploration, Simulink co-simulation and solver diagnostics. CarSim 2024.0 is the tested solver. After one GUI base expansion per vehicle, the batch workflow uses the CLI and writes scenario artifacts outside the database. Optional research workflows (manifest-tracked data generation, estimator validation, sensor replay) layer on top and are never required for ordinary operation. Verification results distinguish Python tests, licensed solver runs and manual agent-behavior evals.

## What it does

| Task | How |
|---|---|
| First task on a machine | `scripts/setup_paths.py` — discovers and validates install paths; lists base candidates for explicit selection |
| Run a scenario headless | `scripts/carsim_batch.py` generates `override.par` + `simfile.sim`, calls the solver CLI, and verifies success |
| Run a scenario from YAML (manifest + validation) | `scripts/scenario_runner.py` — typed scenario YAML, base resolved by name + SHA256, compile-time checks, `run_manifest.json` |
| Change speed / steering / friction / duration | keyword overrides appended after a GUI-expanded base (CarSim parses last-write-wins) |
| Set sprung mass, CG and yaw inertia | `VehicleOverrides(sprung_mass_kg=..., cg_y_m=..., izz_kgm2=...)`; SI inputs convert internally |
| Change any other CarSim keyword | confirm it with `scripts/database_tools.py` (read-only search), then `ScalarOverride` / `unsafe_extra_lines` — never guess a keyword |
| Switch to another vehicle | one-time GUI base expansion, then override everything else |
| Read results | `read_run_csv()` → SI DataFrame of every registered channel (`units="native"` for raw values; unknown units fail, never guessed) |
| Close the loop in Simulink | co-simulation via the `vs_sf` S-Function — `examples/simulink_cosim.py` + `scripts/cosim_model.m` (PI yaw-tracking demo, verified end to end) |
| Torque vectoring / TCS / event tests | per-wheel torque imports (`examples/torque_vectoring.py` — zero-steer yaw verified), open-loop throttle/brake tables, FSAE acceleration/braking patterns |
| Explore the vehicle database | read-only Python API `scripts/database_tools.py` (datasets, keywords, PARSFILE trees, echo) + grep recipes in `references/` |
| Understand dataset files | `.par` syntax templates in `references/` |
| Batch runs / sweeps | `examples/param_sweep.py`, experiment YAML templates |

## Optional research workflows

On top of the core runtime, for data-driven studies only (never required to run CarSim):

- **Manifest-tracked data generation / identification** — `scripts/experiment_runner.py` + typed scenario YAML: vehicle hash binding, run manifests, post-run validation. See [workflows/research-experiments.md](references/workflows/research-experiments.md).
- **Estimator validation** — declared hardware channels, privileged-channel isolation (`GroundTruthLeakageError`), causal sensor replay. See [workflows/estimator-validation.md](references/workflows/estimator-validation.md).
- **Channel units & categories** — [channel-registry.md](references/channel-registry.md).

## Install

Clone the repo into your agent's skills directory:

```bash
# cross-tool standard (personal / project)
git clone https://github.com/zyfgi/carsim-guide-skill ~/.agents/skills/carsim-guide
git clone https://github.com/zyfgi/carsim-guide-skill .agents/skills/carsim-guide

# Claude Code
git clone https://github.com/zyfgi/carsim-guide-skill ~/.claude/skills/carsim-guide

# or keep the repo wherever you like and link it in
git clone https://github.com/zyfgi/carsim-guide-skill ~/src/carsim-guide-skill
ln -s ~/src/carsim-guide-skill ~/.agents/skills/carsim-guide    # macOS / Linux
# Windows (cmd, admin): mklink /D "%USERPROFILE%\.agents\skills\carsim-guide" "C:\src\carsim-guide-skill"
```

Or hand the install to your agent — paste this prompt:

```text
Install the carsim-guide agent skill for me:
1. Clone https://github.com/zyfgi/carsim-guide-skill into a skills directory
   (~/.agents/skills/carsim-guide, or ~/.claude/skills/carsim-guide for
   Claude Code, or .agents/skills/carsim-guide in this project).
2. If git is unavailable or blocked, fetch the ZIP from
   https://github.com/zyfgi/carsim-guide-skill/archive/refs/heads/master.zip
   and extract it to the same target.
3. Verify SKILL.md exists in the installed carsim-guide folder and show me
   its name/description to confirm the install.
4. If CarSim is installed on this machine, run
   `python scripts/setup_paths.py` once (from the installed folder) to
   discover and cache the CarSim install paths for all future sessions.
```

Using an agent without skill support? Add one line to your `AGENTS.md` / rules file: `For CarSim execution, configuration, or automation tasks, read SKILL.md in carsim-guide-skill.`

### Optional companion (Simulink-heavy work)

The co-simulation path above is self-contained — `scripts/cosim_model.m` + `examples/simulink_cosim.py` run with plain MATLAB/Simulink, no extra skills needed. If your agent will also *design and build* nontrivial Simulink models (controller architectures, Model-Based Design practice), add MathWorks' official skills alongside:

```bash
git clone --depth 1 https://github.com/matlab/simulink-agentic-toolkit /tmp/satk
cp -r /tmp/satk/skills-catalog/{simulink-modeling,simulink-simulation,simulink-environment-fundamentals,control-systems} ~/.agents/skills/
```

(adjust the target to your agent's skills directory, e.g. `~/.claude/skills/`). These are MathWorks' skills under their own license (use in conjunction with MathWorks products) and are deliberately **not vendored** into this repo — the install command always fetches the current upstream version.

## Use it

After installation, just mention the task in plain language:

- "Use CarSim to run a 65 s straight cruise at 50 km/h with the four-motor EV."
- "Switch to the C-Class hatchback and rerun the same scenario at μ = 0.5."
- "Add a +120 kg central payload variant and verify the static axle loads."
- "Read the yaw-rate column from the last run and convert it to rad/s."
- "Put a Simulink PI controller in the loop and hold the yaw rate at 0.15 rad/s."

The skill triggers on CarSim execution, configuration and automation; generic vehicle-dynamics theory does not require it. `SKILL.md` is the entry point.

**First CarSim task on a machine**: the agent runs `scripts/setup_paths.py` once (SKILL.md §0, step 0) — about one second of scanning, then the install paths live in `~/.carsim_guide_paths.json` and later sessions reuse the cache, revalidate required paths and verify a bound base hash.

### Research workflow (optional)

1. Inspect the vehicle/Run Control in a GUI-expanded base, then bind it with
   `scripts/vehicle_registry.py` (explicit name, path, SHA256, version and identity).
2. Start with an [example YAML](examples/basic_run.yaml); choose the actual hardware
   whitelist and optionally sampling, delay, noise, bias, quantization, jitter and drops.
3. Compile with `python scripts/experiment_runner.py examples/basic_run.yaml --registry vehicles.local.json --out runs`.
4. Add `--run` with a fresh output root to execute and validate. Accepted runs produce
   SI observations, separate evaluation data, sensor packets and `manifest.json`.

See [research experiments](references/workflows/research-experiments.md),
[channel units](references/channel-registry.md) and
[estimator boundaries](references/workflows/estimator-validation.md) for the exact contract.
Templates for friction/mass sweeps, tire forces and vehicle parameter identification
are in `examples/`. They generate data; model training and identifiability analysis
depend on the research design.

**Migration (core readers):** `read_run_csv()` returns every registered channel —
tire outputs included — in SI by default (`units="native"` for raw CarSim values).
The old `allow_truth=` flag is a deprecated no-op; estimator/evaluator isolation now
lives only in the optional workflow (`load_run(..., estimator_channels=[...])`).
Motor speeds use rad/s; unknown units fail instead of silently passing through;
old newest-base caches require explicit rebinding; `extra_lines` is deprecated in
favor of typed parameters or the advanced `unsafe_extra_lines` escape hatch.

## Requirements

- CarSim 2024.0 (Windows x64) with a valid license — GUI open or `cslm.exe` running
- Python 3.8+ with pandas, NumPy, PyYAML and jsonschema — `pip install -r requirements.txt`

**Verified environments**: CarSim 2024.0, Windows 10/11 x64, Python 3.14 + pandas 3.0; MATLAB **R2025b** + Simulink 25.2 for the co-simulation path (works despite being newer than CarSim 2024.0's officially tested range). Any reasonably recent Python 3 + pandas should work.

**Other CarSim versions**: the simfile version is inferred from standard install names or supplied explicitly for custom paths. Registry/version disagreement fails. Other releases still require solver acceptance testing; version inference does not establish compatibility.

### How this differs from a CarSim MCP server

| | carsim-guide-skill | A CarSim MCP server |
|---|---|---|
| Protocol | Agent Skills standard (`SKILL.md`) | MCP server + MCP client |
| Dependencies | plain CLI + Python (pandas) | MCP host support + server config |
| Database access | read-only (override.par instead) | direct dataset read/write tools |
| Best for | batch runs, sweeps, scripted pipelines | interactive dataset exploration/editing |

The two coexist fine: the skill treats a configured MCP server as an optional exploration accelerator and routes all running/reading through its own scripts (SKILL.md §8).

## Repository layout

```
SKILL.md                           # entry point: mechanics, override pattern, channels & units, pitfalls
scripts/setup_paths.py             # one-time install discovery -> cached paths (first run on a machine)
scripts/carsim_batch.py            # generate / run / read workflow (CLI + library API)
scripts/scenario_schema.py         # typed config + generic scenario YAML validation
scripts/scenario_runner.py         # generic scenario runner: YAML -> run_manifest.json
scripts/base_registry.py           # explicit base identity and SHA256 (name binding)
scripts/parameters.py              # ScalarOverride framework + verified parameter registry
scripts/database_tools.py          # read-only database exploration API
scripts/vehicle_registry.py        # deprecated compat wrapper over base_registry
scripts/experiment_runner.py       # compile / run / validate / manifest (optional research workflow)
scripts/result_contract.py         # core channel registry: native units, SI factors, categories
scripts/workflows/                 # optional workflow layer (estimator validation); core never imports it
scripts/sensor_replay.py           # causal seeded sensor packets (optional research workflow)
scripts/validate_run.py            # fresh complete results and echoed parameters
schemas/experiment.schema.json     # strict experiment schema v1
scripts/cosim_model.m              # Simulink co-sim model builder (matlab -batch)
scripts/tv_cosim.m                 # torque-vectoring co-sim model builder
scripts/dump_dll_exports.py        # zero-dependency DLL export-symbol enumerator
examples/scenarios/                # generic scenario YAML examples (cruise, friction, steering, tire forces, overrides)
examples/param_sweep.py            # runnable batch parameter-sweep example
examples/simulink_cosim.py         # runnable Simulink+CarSim closed-loop demo
examples/torque_vectoring.py       # runnable torque-vectoring demo (zero-steer yaw)
tests/                             # unit tests (CI) + solver-in-loop functional checks (auto-skip without CarSim)
evals/evals.json                   # manual trigger/behavior cases (core workflows, negative triggers)
evals/README.md                    # protocols and versioned executable evidence
evals/run_checks.py               # pytest + licensed manifest verification → JSON records
references/python-interface.md     # script walkthrough + unit conversion contract
references/database-exploration.md # database exploration: database_tools API + grep recipes
references/scenarios.md            # generic scenario YAML contract + scenario_runner
references/parameters.md           # parameter override tiers + unknown-keyword workflow
references/run-validation.md       # compile-time + post-run validation semantics
references/dataset-syntax.md       # .par dataset syntax templates
references/advanced-controls.md    # open-loop controls, torque imports, table semantics, FSAE notes
references/simulink-cosim.md       # Simulink co-simulation: verified recipe + pitfalls
references/vs-c-api.md             # VS C API stepping fallback (prototype)
references/workflows/              # optional research workflows (data generation, estimator validation)
.github/workflows/ci.yml           # frontmatter / syntax / size / eval-structure checks on push
```

## Disclaimer

Field-tested against CarSim 2024.0 on Windows x64; the verification assets ship in the repo (`tests/` — unit tests run anywhere, functional checks run wherever CarSim + a license are present and skip otherwise; `evals/README.md` — the trigger/behavior protocol). Behavior may vary with other versions or setups. Test in your own environment before relying on it for critical work.

## License

MIT — see [LICENSE](LICENSE).
