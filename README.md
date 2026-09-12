# carsim-guide-skill

A self-contained **AI agent skill** for operating **CarSim 2024.0** headless — no GUI after setup, no database writes, no Simulink, no MCP server required. Everything here was validated by actually running it end to end (multi-scenario batch runs, unit checks, sign-convention checks, vehicle switching, error paths).

## What it gives you

- **The override.par pattern** — the verified way to run CarSim scenarios without touching the GUI: take a GUI-expanded `Run_all.par` as a base once per vehicle, then append keyword overrides (speed table, steering, friction, output channels) for every scenario. CarSim parses last-write-wins, so overrides just work.
- **`scripts/carsim_batch.py`** — a parameterized Python workflow: generate `override.par` + `simfile.sim`, call `VS_SolverWrapper_CLI_64.exe` headless with proper success/failure detection, and read the 1 kHz `run.csv` back as a **SI-unit pandas DataFrame** (unit contract built in and field-verified: km/h, g, rpm, deg/s conversions).
- **Hard-won pitfall knowledge** — two falsified approaches (thin-parsfile direct reads segfault; the VS C API stepping is unnecessary for most online-validation work), the steering-table append trap, the 32-bit DLL trap, license requirements, path-escaping traps, and more.
- **Database exploration without any tooling** — the CarSim database is plain-text `.par` files; grep recipes cover vehicle search, assembly trees, and keyword/unit lookups.
- **Dataset syntax templates** — Run Control / Procedure / speed controller / path follower / Segment-Builder roads, for reading or editing via GUI.

## Install

**As a ZCode (or compatible) skill** — clone into your skills directory:

```bash
# personal (all projects)
git clone https://github.com/zyfgi/carsim-guide-skill ~/.agents/skills/carsim-guide
# or project-level
git clone https://github.com/zyfgi/carsim-guide-skill .agents/skills/carsim-guide
```

The skill auto-triggers on any CarSim-related task. It is equally usable **standalone**: `scripts/carsim_batch.py` has no dependencies beyond Python 3 + pandas and works without the skill system.

## Quick start (fresh machine → first run)

1. Locate the CarSim install (`<PROG>` = `…\CarSim2024.0_Prog`, `<DATADIR>` = `…\CarSim2024.0_Data`).
2. License: keep the CarSim GUI open, or start `<PROG>\Programs\cslm.exe`.
3. Get a base (once per vehicle — the only GUI step): open a Run Control → **Run Math Model** → take `Results\Run_<uuid>\Run_all.par`.
4. Run a 65 s straight cruise:

```bash
python scripts/carsim_batch.py \
    --prog    "C:/CarSim/CarSim2024.0_Prog" \
    --datadir "C:/CarSim/CarSim2024.0_Data" \
    --base    "C:/work/base/Run_all.par" \
    --out     "C:/work/demo" \
    --tstop 65 --speed-profile "0:50,65:50" --run --read
```

5. Acceptance: stdout ends with `Termination at simulation time = 65 s` and `<out>/run.csv` exists (1 kHz, SI-ready).

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
