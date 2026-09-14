> This skill follows the [Agent Skills](https://agentskills.io) standard: a folder with a `SKILL.md` (YAML frontmatter + instructions), bundled scripts, and on-demand references.

# CarSim Guide

A skill for configuring and running CarSim headless, with a research experiment contract for reproducible datasets. It supports typed scenarios, named vehicle/base bindings with SHA256, SI channel units, estimator/evaluator separation, sensor replay and post-run validation. CarSim 2024.0 is the tested solver; Simulink co-simulation remains available through the existing optional demos. After one GUI base expansion per vehicle, the batch workflow uses the CLI and writes scenario artifacts outside the database. Verification results distinguish Python tests, licensed solver runs and manual agent-behavior evals.

## What it does

| Task | How |
|---|---|
| First task on a machine | `scripts/setup_paths.py` — discovers and validates install paths; lists base candidates for explicit selection |
| Reproducible research experiments | `scripts/experiment_runner.py` — validated YAML/JSON, vehicle hash, manifest, acceptance checks and sensor packets |
| Run a scenario headless | `scripts/carsim_batch.py` generates `override.par` + `simfile.sim`, calls the solver CLI, and verifies success |
| Change speed / steering / friction / duration | keyword overrides appended after a GUI-expanded base (CarSim parses last-write-wins) |
| Set sprung mass, CG and yaw inertia | `VehicleOverrides(sprung_mass_kg=..., cg_y_m=..., izz_kgm2=...)`; SI inputs convert internally |
| Switch to another vehicle | one-time GUI base expansion, then override everything else |
| Read results | `load_run()` → SI observable/truth partitions; explicit channel units, no unknown-unit fallback |
| Close the loop in Simulink | co-simulation via the `vs_sf` S-Function — `examples/simulink_cosim.py` + `scripts/cosim_model.m` (PI yaw-tracking demo, verified end to end) |
| Torque vectoring / TCS / event tests | per-wheel torque imports (`examples/torque_vectoring.py` — zero-steer yaw verified), open-loop throttle/brake tables, FSAE acceleration/braking patterns |
| Explore the vehicle database | grep recipes in `references/` — no tooling required |
| Understand dataset files | `.par` syntax templates in `references/` |

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

### Research workflow

1. Inspect the vehicle/Run Control in a GUI-expanded base, then bind it with
   `scripts/vehicle_registry.py` (explicit name, path, SHA256, version and identity).
2. Start with an [example YAML](examples/basic_run.yaml); choose the actual hardware
   whitelist and optionally sampling, delay, noise, bias, quantization, jitter and drops.
3. Compile with `python scripts/experiment_runner.py examples/basic_run.yaml --registry vehicles.local.json --out runs`.
4. Add `--run` with a fresh output root to execute and validate. Accepted runs produce
   SI observations, separate evaluation data, sensor packets and `manifest.json`.

See [research experiments](references/research-experiments.md),
[channel units](references/channel-registry.md) and
[estimator boundaries](references/estimator-validation.md) for the exact contract.
Templates for friction/mass sweeps, tire forces and vehicle parameter identification
are in `examples/`. They generate data; model training and identifiability analysis
depend on the research design.

**Migration:** the default CSV reader no longer returns truth channels; evaluator
code must request `allow_truth=True` or `evaluator_view()`. Motor speeds now use rad/s.
Unknown units fail instead of silently passing through. Old newest-base caches require
explicit rebinding. `extra_lines` is deprecated in favor of typed parameters or the
advanced `unsafe_extra_lines` escape hatch.

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
scripts/scenario_schema.py         # typed config and semantic validation
scripts/vehicle_registry.py        # explicit base identity and SHA256
scripts/experiment_runner.py       # compile / run / validate / manifest
scripts/result_contract.py         # explicit units, observable and evaluator access
scripts/sensor_replay.py           # causal seeded sensor packets
scripts/validate_run.py            # fresh complete results and echoed parameters
schemas/experiment.schema.json     # strict experiment schema v1
scripts/cosim_model.m              # Simulink co-sim model builder (matlab -batch)
scripts/tv_cosim.m                 # torque-vectoring co-sim model builder
scripts/dump_dll_exports.py        # zero-dependency DLL export-symbol enumerator
examples/param_sweep.py            # runnable batch parameter-sweep example
examples/simulink_cosim.py         # runnable Simulink+CarSim closed-loop demo
examples/torque_vectoring.py       # runnable torque-vectoring demo (zero-steer yaw)
tests/                             # unit tests (CI) + solver-in-loop functional checks (auto-skip without CarSim)
evals/evals.json                   # manual trigger/behavior cases, including research isolation
evals/README.md                    # protocols and versioned executable evidence
evals/run_checks.py               # pytest + licensed manifest verification → JSON records
references/python-interface.md     # script walkthrough + unit conversion contract
references/database-exploration.md # grep-based database exploration (no MCP)
references/dataset-syntax.md       # .par dataset syntax templates
references/advanced-controls.md    # open-loop controls, torque imports, table semantics, FSAE notes
references/simulink-cosim.md       # Simulink co-simulation: verified recipe + pitfalls
references/vs-c-api.md             # VS C API stepping fallback (prototype)
.github/workflows/ci.yml           # frontmatter / syntax / size / eval-structure checks on push
```

## Disclaimer

Field-tested against CarSim 2024.0 on Windows x64; the verification assets ship in the repo (`tests/` — unit tests run anywhere, functional checks run wherever CarSim + a license are present and skip otherwise; `evals/README.md` — the trigger/behavior protocol). Behavior may vary with other versions or setups. Test in your own environment before relying on it for critical work.

## License

MIT — see [LICENSE](LICENSE).
