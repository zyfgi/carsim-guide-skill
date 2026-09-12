# carsim-guide-skill

A self-contained knowledge pack + Python tooling for operating **CarSim 2024.0** headless — no GUI after setup, no database writes, no Simulink, no MCP server required. Everything here was validated by actually running it end to end (multi-scenario batch runs, unit checks, sign-convention checks, vehicle switching, error paths).

Built for **AI agents**: install once, then your agent drives CarSim through it. The scripts also run standalone (CI-friendly).

## What it gives you

- **The override.par pattern** — the verified way to run CarSim scenarios without touching the GUI: take a GUI-expanded `Run_all.par` as a base once per vehicle, then append keyword overrides (speed table, steering, friction, output channels) for every scenario. CarSim parses last-write-wins, so overrides just work.
- **`scripts/carsim_batch.py`** — a parameterized Python workflow: generate `override.par` + `simfile.sim`, call `VS_SolverWrapper_CLI_64.exe` headless with proper success/failure detection, and read the 1 kHz `run.csv` back as a **SI-unit pandas DataFrame** (unit contract built in and field-verified: km/h, g, rpm, deg/s conversions).
- **Hard-won pitfall knowledge** — two falsified approaches (thin-parsfile direct reads segfault; the VS C API stepping is unnecessary for most online-validation work), the steering-table append trap, the 32-bit DLL trap, license requirements, path-escaping traps, and more.
- **Database exploration without any tooling** — the CarSim database is plain-text `.par` files; grep recipes cover vehicle search, assembly trees, and keyword/unit lookups.
- **Dataset syntax templates** — Run Control / Procedure / speed controller / path follower / Segment-Builder roads, for reading or editing via GUI.

## Install

**Option A — as an agent skill (any agent that supports the Agent Skills convention, i.e. a `SKILL.md` with YAML frontmatter).** Clone the repo into your agent's skills directory; the skill auto-triggers on CarSim-related tasks. Common locations:

```bash
# cross-tool standard (personal / project-level)
git clone https://github.com/zyfgi/carsim-guide-skill ~/.agents/skills/carsim-guide
git clone https://github.com/zyfgi/carsim-guide-skill .agents/skills/carsim-guide

# Claude Code
git clone https://github.com/zyfgi/carsim-guide-skill ~/.claude/skills/carsim-guide
```

If your agent uses a different directory, check its docs — anything that discovers `SKILL.md` files works.

**Option B — as plain context (agents without skill support).** The whole pack is ordinary Markdown. Just point your agent at it, e.g. add one line to your `AGENTS.md` / rules file:

```
For any CarSim task, read SKILL.md in carsim-guide-skill first and follow it.
```

**Option C — standalone, no agent.** `scripts/carsim_batch.py` has no dependencies beyond Python 3 + pandas and works on its own (see Quick start).

### Zero-effort: let your agent install it

Paste this prompt into any AI coding agent — it will do the whole install end to end:

```text
Install the carsim-guide agent skill for me:
1. Clone https://github.com/zyfgi/carsim-guide-skill into a skills directory.
   Preferred target: ~/.agents/skills/carsim-guide (cross-tool standard).
   Alternatives: ~/.claude/skills/carsim-guide (Claude Code), or
   .agents/skills/carsim-guide in the current project.
2. If git is unavailable or blocked, download the ZIP from
   https://github.com/zyfgi/carsim-guide-skill/archive/refs/heads/master.zip
   and extract it to the same target.
3. Verify SKILL.md exists inside the installed carsim-guide folder and show
   me its name/description frontmatter to confirm the install.
```

## After install

This skill is designed to be **executed by an agent**, not read as a human tutorial. Once installed, your agent loads `SKILL.md` automatically on any CarSim-related task and runs the verified workflow end to end — locating the installation, generating the one-time vehicle base, headless scenario runs, SI-unit CSV results. (`SKILL.md` §0 is the 5-step quick start it follows.)

If you are an agent that was pointed at this repository directly: read [`SKILL.md`](SKILL.md) now — it is the entry point. `scripts/carsim_batch.py` is the run workflow (CLI + library API); the files under `references/` are read on demand, exactly as SKILL.md instructs.

## Requirements

- CarSim 2024.0 installed with a valid license (GUI open or `cslm.exe` running)
- Python 3.x with pandas (any conda/venv; CarSim's bundled Python is not used)

## Repository layout

```
SKILL.md                          # main guide: mechanics, override pattern, channels & units, pitfalls
scripts/carsim_batch.py           # generate / run / read workflow (CLI + library API)
scripts/dump_dll_exports.py       # zero-dependency DLL export-symbol enumerator
references/python-interface.md    # script walkthrough + unit conversion contract
references/database-exploration.md# grep-based database exploration (no MCP)
references/dataset-syntax.md      # .par dataset syntax templates
```

## License

MIT — see [LICENSE](LICENSE).
