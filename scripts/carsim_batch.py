#!/usr/bin/env python3
"""CarSim 2024.0 headless batch runner: override.par + simfile.sim + CLI + CSV.

Verified workflow (after the ONE-TIME GUI base expansion, no GUI, no database
writes, no Simulink, no VS C API):

  1. base Run_all.par   - GUI-expanded vehicle run, generated once per vehicle
                          (open the Run Control in the GUI, click "Run Math
                          Model", take Results\\Run_<uuid>\\Run_all.par)
  2. override.par       - appended AFTER the base reference; CarSim parses
                          last-write-wins, so keywords/tables set here simply
                          override the base (speed table, steering, friction,
                          output channels)
  3. simfile.sim        - self-contained run description; ERDFILE points to
                          run.csv and OPT_VS_FILETYPE 4 makes the solver write
                          plain-text CSV
  4. VS_SolverWrapper_CLI_64.exe -sim <simfile>   - headless solver call
  5. run.csv            - 1 kHz text CSV, read directly with pandas

License: the solver DLL/CLI needs the CarSim GUI running, or cslm.exe
started from <PROG>\\Programs. Without it expect a license error.

Usage example (straight cruise at 50 km/h for 65 s, then read the CSV):

  python carsim_batch.py ^
      --prog    "C:/CarSim/CarSim2024.0_Prog" ^
      --datadir "C:/CarSim/CarSim2024.0_Data" ^
      --base    "C:/work/base/Run_all.par" ^
      --out     "C:/work/demo_straight" ^
      --tstop 65 --speed-profile "0:50,65:50" --run --read

After `python setup_paths.py` has run once on the machine, --prog/--datadir/
--base can be omitted: they default to environment variables (CARSIM_PROG /
CARSIM_DATADIR / CARSIM_BASE), then to the cache file
~/.carsim_guide_paths.json. Only --out is ever required.

Profiles are comma-separated "time:value" pairs, time in s, speed in km/h,
steering-wheel angle in deg. Omit --speed-profile for a constant 50 km/h.
"""
import argparse
import json
import logging
import os
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("carsim_batch")

TSTEP = 0.001  # integration step [s]; IPRINT=1 -> CSV row per step (1 kHz)

# ---------------------------------------------------------------------------
# Install-path resolution: explicit argument > environment variable > cache
# written by scripts/setup_paths.py (first-run discovery, one-time per machine).
CONFIG_ENV = "CARSIM_GUIDE_CONFIG"
ENV_KEYS = {"prog": "CARSIM_PROG", "datadir": "CARSIM_DATADIR",
            "base_run_all": "CARSIM_BASE"}


def cached_paths():
    """Read the setup_paths.py cache; returns {} when absent or corrupt."""
    try:
        p = Path(os.environ.get(
            CONFIG_ENV, str(Path.home() / ".carsim_guide_paths.json")))
        cfg = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return cfg if isinstance(cfg, dict) else {}


def resolve_paths(prog=None, datadir=None, base=None,
                  require=("prog", "datadir", "base_run_all")):
    """Fill missing install paths and return (prog, datadir, base).

    Precedence per key: explicit argument > env var (CARSIM_PROG /
    CARSIM_DATADIR / CARSIM_BASE) > ~/.carsim_guide_paths.json (written once
    by scripts/setup_paths.py). Raises RuntimeError with a setup hint for
    anything still missing, so callers never fail with a bare TypeError.
    """
    given = {"prog": prog, "datadir": datadir, "base_run_all": base}
    cached = cached_paths()
    out = {}
    for key in ("prog", "datadir", "base_run_all"):
        val = given[key] or os.environ.get(ENV_KEYS[key]) or cached.get(key)
        if not val and key in require:
            raise RuntimeError(
                "%s not set. Pass it explicitly, set %s, or run "
                "scripts/setup_paths.py once (discovers and caches CarSim "
                "paths for all later sessions)." % (key, ENV_KEYS[key]))
        out[key] = val
    return out["prog"], out["datadir"], out["base_run_all"]

# ---------------------------------------------------------------------------
# ERD output channels (WRT_<name> keywords in override.par).
# A proven set for vehicle-dynamics identification work: cg states, four wheel
# speeds/torques/steer angles, tire forces & slips (ground truth - evaluation
# only!), roll/pitch for IMU gravity projection, four motor speeds.
# NOTE: WRT_ROLL / WRT_PITCH appear in the CSV header as "Roll" / "Pitch".
OUTPUTS_CORE = [
    "Vx", "Vy", "Ax", "Ay", "AVz",
    "Steer_L1", "Steer_R1", "Steer_L2", "Steer_R2",
    "AVy_L1", "AVy_R1", "AVy_L2", "AVy_R2",
    "My_Dr_L1", "My_Dr_R1", "My_Dr_L2", "My_Dr_R2",
    "My_Bk_L1", "My_Bk_R1", "My_Bk_L2", "My_Bk_R2",
    "Fx_L1", "Fx_R1", "Fx_L2", "Fx_R2",
    "Fy_L1", "Fy_R1", "Fy_L2", "Fy_R2",
    "Fz_L1", "Fz_R1", "Fz_L2", "Fz_R2",
    "Kappa_L1", "Kappa_R1", "Kappa_L2", "Kappa_R2",
    "Alpha_L1", "Alpha_R1", "Alpha_L2", "Alpha_R2",
]
OUTPUTS_EXTRA = [
    "ROLL", "PITCH",            # Euler angles [deg] - gravity projection
    "AV_Mt_D1_L", "AV_Mt_D1_R", "AV_Mt_D2_L", "AV_Mt_D2_R",  # motor speeds [rpm]
]

# Wheel corner naming used by CarSim channels (global convention):
#   L1=FL  R1=FR  L2=RL  R2=RR   (axle 1 = front, 2 = rear)

# ---------------------------------------------------------------------------
# CSV unit contract -> SI (all scales verified against solver output).
#   Vx/Vy  km/h->m/s     Ax/Ay  g->m/s^2    AVz/angles  deg(/s)->rad(/s)
#   AVy_*  rpm->rad/s    forces/torques already SI
SI_SCALES = [
    ("vx", 0.2777778), ("vy", 0.2777778),
    ("ax", 9.81), ("ay", 9.81),
    ("avz", 0.0174533), ("roll", 0.0174533), ("pitch", 0.0174533),
    ("yaw", 0.0174533), ("alpha", 0.0174533),
    ("steer", 0.0174533),
    ("avy", 0.1047198),          # wheel spin: rpm -> rad/s
]

# Channels that are simulator ground truth. If an estimator/consumer must stay
# "blind" to internal states (e.g. online validation), keep these OUT of it and
# use them only for evaluation. Observable states = everything else above.
TRUTH_ONLY_PREFIXES = ("Fx_", "Fy_", "Fz_", "Kappa_", "Alpha_")
UNRELIABLE_COLS = ("Lat_Veh", "Lat_Targ")  # known-drift artifacts; use Yo/Yaw


def si_scale(col):
    """Return the multiply-to-SI factor for a run.csv column name.

    Matching is exact or underscore-delimited: "Vx" and "Vx_R1" match the "vx"
    rule, while "AVYX" or "AV_Trans" do not - so unrelated columns are never
    silently rescaled. Unknown identities stay at 1.0 and read_run_csv warns
    about them.
    """
    c = col.lower()
    if c == "time":
        return 1.0
    for prefix, scale in SI_SCALES:
        if c == prefix or c.startswith(prefix + "_"):
            return scale
    return 1.0  # forces N, torques N.m, kappa -, motor rpm kept as-is, etc.


def _known_unit(col):
    """True if a column's identity is covered by the verified unit contract
    (SI forces/torques, dimensionless kappa, motor rpm, generic time/id)."""
    c = col.lower()
    return (c.startswith(("fx_", "fy_", "fz_", "my_", "kappa_", "av_mt_", "time"))
            or c in ("station", "xo", "yo", "yaw", "zo"))


# ---------------------------------------------------------------------------
# 1) generators
# ---------------------------------------------------------------------------
def _table(name, rows, interp="LINEAR_FLAT"):
    """CarSim ENDTABLE block: header, 'x, y' rows, ENDTABLE."""
    lines = ["%s %s" % (name, interp)]
    lines += ["%.6f, %.6f" % (x, y) for x, y in rows]
    lines.append("ENDTABLE")
    return lines


def _dedupe(rows):
    """Drop repeated x values - CarSim rejects tables with duplicate abcissa."""
    out, last = [], None
    for t, v in rows:
        if last is not None and abs(t - last) < 1e-9:
            continue
        out.append((t, v))
        last = t
    return out


def override_par(base_run_all, tstop, speed_rows, steer_rows,
                 outputs=None, mu=0.9, tstep=TSTEP, extra_lines=()):
    """Build override.par text: base reference + run switches + control tables.

    Key switches (see SKILL.md section 3 for the full rationale):
      OPT_ERROR_DIALOG 0  headless: never pop a dialog
      OPT_VS_FILETYPE 4   ERD output as plain-text CSV
      OPT_ALL_WRITE 0     only the WRT_* channels below are written
      OPT_STOP 0 + SSTOP  disable early stop-on-distance
      OPT_SC 1            closed-loop speed controller, target = table
      OPT_DM 0            open-loop steering: STEER_SW_TABLE is the only
                          steering override mechanism verified to REPLACE the
                          base table (closed-loop LTARG tables APPEND rows
                          instead - known trap)
      MU_ROAD_CARPET      friction override; set mu to match the base road or
                          the intended scenario (a low-mu base needs this to
                          run ordinary scenarios)
    extra_lines: extra keyword lines inserted after the control tables and
      before the WRT declarations - the standard slot for parameter overrides
      such as static payloads: ["M_SU 1254.0", "IZZ_SU 1743.1"].
    """
    outputs = outputs if outputs is not None else OUTPUTS_CORE + OUTPUTS_EXTRA
    lines = [
        "PARSFILE", "PARSFILE " + base_run_all,
        "OPT_ERROR_DIALOG 0", "OPT_ALL_WRITE 0", "OPT_VS_FILETYPE 4",
        "TSTART 0", "TSTOP %.6f" % tstop,
        "OPT_STOP 0", "SSTOP 100000",
        "TSTEP %.7f" % tstep, "IPRINT %d" % 1,
        "INSTALL_SPEED_CONTROLLER", "OPT_SC 1", "OPT_BK_SC 1",
        "OPT_SC_ENGINE_BRAKING 1",          # EV: prefer regen braking
        "SPEED_TARGET_CONSTANT 0", "SPEED_TARGET_S_CONSTANT 0",
        "SPEED_TARGET_COMBINE ADD",
    ]
    # rows: time [s], target speed [km/h]; initial speed = first row
    lines += _table("SPEED_TARGET_TABLE", _dedupe(speed_rows))
    # rows: s_left, mu_left, mu_right - uniform friction strip across lane
    lines += ["MU_ROAD_CARPET 2D_STEP",
              "0, -20, 20",
              "-500, %.6f, %.6f" % (mu, mu),
              "1000, %.6f, %.6f" % (mu, mu),
              "ENDTABLE"]
    # rows: time [s], steering wheel angle [deg] - open loop
    lines += ["OPT_DM 0", "OPT_STR_BY_TRQ 0"]
    lines += _table("STEER_SW_TABLE", _dedupe(steer_rows))
    lines += list(extra_lines)  # parameter overrides (e.g. static payloads)
    lines += ["WRT_" + name for name in outputs]
    lines += ["LOG_ENTRY scenario override", "END", ""]
    return "\n".join(lines)


def simfile(session_dir, prog, datadir, tstep=TSTEP):
    """Build a self-contained simfile.sim writing all outputs into session_dir."""
    p = lambda name: os.path.join(session_dir, name)
    return "\n".join([
        "SIMFILE",
        "FILEBASE " + p("run"),
        "INPUT " + p("override.par"),
        "INPUTARCHIVE " + p("run_all.par"),
        "ECHO " + p("run_echo.par"),        # parsed-model echo: variable proof
        "FINAL " + p("run_end.par"),
        "LOGFILE " + p("run_log.txt"),      # lists every dataset actually used
        "ERDFILE " + p("run.csv"),          # OPT_VS_FILETYPE 4 -> CSV
        "PROGDIR " + prog,
        "DATADIR " + datadir,
        "PRODUCT_ID CarSim", "PRODUCT_VER 2024.0", "VEHICLE_CODE i_i",
        "EXT_MODEL_STEP %.8f" % tstep,
        "PORTS_IMP 0", "PORTS_EXP 0",
        # always pin the 64-bit solver; GUI-generated simfiles may say 32-bit
        "DLLFILE " + os.path.join(prog, "Programs", "solvers", "carsim_64.dll"),
        "END", "",
    ])


def make_scenario(out_dir, base_run_all=None, prog=None, datadir=None,
                  tstop=65.0, speed_rows=None, steer_rows=None, **kw):
    """Write <out_dir>/{override.par, simfile.sim}. Returns the simfile path.

    base_run_all / prog / datadir default to the cached install paths
    (resolve_paths): env vars, then the setup_paths.py cache.
    """
    prog, datadir, base_run_all = resolve_paths(prog, datadir, base_run_all)
    speed_rows = speed_rows if speed_rows is not None else [(0.0, 50.0),
                                                            (tstop, 50.0)]
    steer_rows = steer_rows if steer_rows is not None else [(0.0, 0.0),
                                                            (tstop, 0.0)]
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "override.par"), "w", newline="\n") as f:
        f.write(override_par(base_run_all, tstop, speed_rows, steer_rows, **kw))
    sim = os.path.join(out_dir, "simfile.sim")
    with open(sim, "w", newline="\n") as f:
        f.write(simfile(out_dir, prog, datadir))
    return sim


# ---------------------------------------------------------------------------
# 2) headless solver call
# ---------------------------------------------------------------------------
def run_solver(simfile_path, prog=None, timeout=600):
    """Run VS_SolverWrapper_CLI_64.exe -sim <simfile> and verify success.

    Uses an argv list (no shell), which sidesteps shell backslash escaping
    issues; the simfile path is still normalized to forward slashes because
    the CLI is happiest with those. Success criterion: stdout ends with
    'Termination at simulation time = <TSTOP>' (the RTIME line is written
    to run_log.txt / run_end.par, not stdout). Raises
    RuntimeError with the output tail otherwise (license problems show up as
    'Unable to load library' - start the GUI or cslm.exe). `prog` defaults to
    the cached install path (resolve_paths).
    """
    prog, _, _ = resolve_paths(prog, require=("prog",))
    exe = os.path.join(prog, "Programs", "VS_SolverWrapper_CLI_64.exe")
    cmd = [exe, "-sim", simfile_path.replace("\\", "/")]
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=timeout, encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0 or "Termination at simulation time" not in out:
        tail = "\n".join(out.splitlines()[-40:])
        raise RuntimeError(
            "solver failed (returncode %d).\n--- output tail ---\n%s"
            % (proc.returncode, tail))
    return out  # caller can grep RTIME etc.


# ---------------------------------------------------------------------------
# 3) CSV reader
# ---------------------------------------------------------------------------
def read_run_csv(path, columns=None):
    """Read run.csv into a pandas DataFrame with SI units.

    `columns` optionally restricts/derestricts the loaded columns (pass
    load-bearing names like ["Time", "Vx", "AVz", "Ax", "Ay"]); large runs
    are ~1 kHz x 100+ columns, so selecting columns saves a lot of memory.
    """
    import pandas as pd
    header = pd.read_csv(path, nrows=0)
    usecols = None if columns is None else [c for c in columns
                                            if c in header.columns]
    df = pd.read_csv(path, usecols=usecols)
    if columns is not None:
        # respect the caller's requested order (pandas returns file order)
        df = df[[c for c in columns if c in df.columns]]
    unknown = [c for c in df.columns if si_scale(c) == 1.0 and not _known_unit(c)]
    if unknown:
        logger.warning("no SI conversion rule for columns %s - returned unscaled; "
                       "verify units before use", unknown)
    drop = [c for c in UNRELIABLE_COLS if c in df.columns]
    if drop:
        df = df.drop(columns=drop)
    for c in df.columns:
        df[c] = df[c] * si_scale(c)
    return df


def summarize(df):
    """One-line-per-channel stats for a quick sanity check after a run."""
    import pandas as pd
    keys = [c for c in ("Time", "Vx", "Ax", "Ay", "AVz") if c in df.columns]
    rows = []
    for c in keys:
        rows.append({"channel": c, "min": df[c].min(), "max": df[c].max(),
                     "final": df[c].iloc[-1]})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CLI demo: generate -> run -> read for a straight constant-speed cruise
# ---------------------------------------------------------------------------
def parse_profile(text, default_value, tstop):
    """'t1:v1,t2:v2,...' -> [(t, v), ...]; constant default if text is None."""
    if text is None:
        return [(0.0, default_value), (tstop, default_value)]
    rows = []
    for part in text.split(","):
        t, v = part.split(":")
        rows.append((float(t), float(v)))
    return rows


def main():
    ap = argparse.ArgumentParser(
        description="CarSim headless batch runner (override.par pattern). "
                    "Install paths default to the setup_paths.py cache.")
    ap.add_argument("--prog", default=None, help="CarSim *_Prog directory "
                    "(default: cached / CARSIM_PROG)")
    ap.add_argument("--datadir", default=None, help="CarSim *_Data directory "
                    "(default: cached / CARSIM_DATADIR)")
    ap.add_argument("--base", default=None,
                    help="GUI-expanded base Run_all.par, absolute path "
                    "(default: cached / CARSIM_BASE)")
    ap.add_argument("--out", required=True, help="scenario output directory")
    ap.add_argument("--tstop", type=float, default=65.0)
    ap.add_argument("--speed-profile", default=None,
                    help='"t:v,..." in s and km/h (default constant 50)')
    ap.add_argument("--steer-profile", default=None,
                    help='"t:v,..." in s and steering-wheel deg (default 0)')
    ap.add_argument("--mu", type=float, default=0.9)
    ap.add_argument("--verbose", action="store_true",
                    help="debug logging (solver command lines, per-step status)")
    ap.add_argument("--run", action="store_true", help="call the solver CLI")
    ap.add_argument("--read", action="store_true", help="read run.csv back")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s")
    prog, datadir, base = resolve_paths(args.prog, args.datadir, args.base)
    logger.debug("prog=%s datadir=%s base=%s out=%s",
                 prog, datadir, base, args.out)

    speed_rows = parse_profile(args.speed_profile, 50.0, args.tstop)
    steer_rows = parse_profile(args.steer_profile, 0.0, args.tstop)

    sim = make_scenario(args.out, base, prog, datadir,
                        args.tstop, speed_rows, steer_rows, mu=args.mu)
    logger.info("wrote %s", sim)

    if args.run:
        logger.debug("solver command: %s -sim %s",
                     os.path.join(prog, "Programs",
                                  "VS_SolverWrapper_CLI_64.exe"),
                     sim.replace("\\", "/"))
        out = run_solver(sim, prog, timeout=args.timeout)
        for line in out.splitlines():
            if "RTIME" in line or "Termination" in line:
                logger.info("%s", line.strip())
    if args.read:
        df = read_run_csv(os.path.join(args.out, "run.csv"))
        print(summarize(df).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
