> This skill follows the [Agent Skills](https://agentskills.io) standard: a folder with a `SKILL.md` (YAML frontmatter + instructions), bundled scripts, and on-demand references.

# CarSim Guide

A skill that teaches an AI agent to operate **CarSim 2024.0** headless — running scenarios, switching vehicles, changing parameters, and reading SI-unit results entirely from the command line. After a one-time setup per vehicle, no GUI, no database writes, no Simulink, and no MCP server are needed. Every mechanism and pitfall in this skill was verified by actually running it (18-check suite: parameter changes, vehicle switching, custom output channels, error paths).

## What it does

| Task | How |
|---|---|
| Run a scenario headless | `scripts/carsim_batch.py` generates `override.par` + `simfile.sim`, calls the solver CLI, and verifies success |
| Change speed / steering / friction / duration | keyword overrides appended after a GUI-expanded base (CarSim parses last-write-wins) |
| Add payloads (mass, CG, inertia, tire radius) | `extra_lines=["M_SU 1254.0", "Y_CG_SU 150.0", …]` |
| Switch to another vehicle | one-time GUI base expansion, then override everything else |
| Read results | `run.csv` → pandas DataFrame in **SI units** (built-in, field-verified contract: km/h, g, rpm, deg/s) |
| Close the loop in Simulink | co-simulation via the `vs_sf` S-Function — `examples/simulink_cosim.py` + `scripts/cosim_model.m` (PI yaw-tracking demo, verified end to end) |
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
```

Using an agent without skill support? Add one line to your `AGENTS.md` / rules file: `For any CarSim task, read SKILL.md in carsim-guide-skill first and follow it.`

## Use it

After installation, just mention the task in plain language:

- "Use CarSim to run a 65 s straight cruise at 50 km/h with the four-motor EV."
- "Switch to the C-Class hatchback and rerun the same scenario at μ = 0.5."
- "Add a +120 kg central payload variant and verify the static axle loads."
- "Read the yaw-rate column from the last run and convert it to rad/s."

The skill auto-triggers on CarSim-related work; `SKILL.md` is the entry point your agent follows.

## Requirements

- CarSim 2024.0 (Windows x64) with a valid license — GUI open or `cslm.exe` running
- Python 3.x with pandas (the scripts also run standalone, e.g. in CI)

**Verified environments**: CarSim 2024.0, Windows 10/11 x64, Python 3.14 + pandas 3.0; MATLAB **R2025b** + Simulink 25.2 for the co-simulation path (works despite being newer than CarSim 2024.0's officially tested range). Any reasonably recent Python 3 + pandas should work.

**Other CarSim versions**: the workflow is version-agnostic in principle — adjust the `CarSim2024.0_Prog/_Data` directory names and `PRODUCT_VER` in the simfile, then re-run the quick-start acceptance check. The pitfall list was verified against 2024.0 only; treat other versions as unverified.

## Repository layout

```
SKILL.md                           # entry point: mechanics, override pattern, channels & units, pitfalls
scripts/carsim_batch.py            # generate / run / read workflow (CLI + library API)
scripts/cosim_model.m              # Simulink co-sim model builder (matlab -batch)
scripts/dump_dll_exports.py        # zero-dependency DLL export-symbol enumerator
examples/param_sweep.py            # runnable batch parameter-sweep example
examples/simulink_cosim.py         # runnable Simulink+CarSim closed-loop demo
evals/evals.json                   # trigger/behavior tests (4 positive, 2 negative, 1 behavior)
references/python-interface.md     # script walkthrough + unit conversion contract
references/database-exploration.md # grep-based database exploration (no MCP)
references/dataset-syntax.md       # .par dataset syntax templates
references/simulink-cosim.md       # Simulink co-simulation: verified recipe + pitfalls
references/vs-c-api.md             # VS C API stepping fallback (prototype)
.github/workflows/ci.yml           # frontmatter / syntax / size checks on push
```

## Disclaimer

Field-tested against CarSim 2024.0 on Windows x64 with an 18-check automated suite; behavior may vary with other versions or setups. Test in your own environment before relying on it for critical work.

## License

MIT — see [LICENSE](LICENSE).
