#!/usr/bin/env python3
"""Discover CarSim install paths once, cache them, then never explore again.

First run on a machine (or after CarSim moves):
    python setup_paths.py              # scan + verify + cache (a few seconds)

Every later session (cheap - no filesystem scanning):
    python setup_paths.py --json       # one compact JSON line with the paths

The cache lives at ~/.carsim_guide_paths.json (override the location with the
CARSIM_GUIDE_CONFIG environment variable - the unit tests do exactly that).
Machine-specific paths therefore never sit inside the skill directory, so they
cannot leak into a repo, and each later agent session reads one short JSON
instead of re-running discovery.

Manual overrides for non-standard installs:
    python setup_paths.py --set prog="D:/.../CarSim2024.0_Prog"
    python setup_paths.py --set base="D:/.../Results/Run_x/Run_all.par"
    python setup_paths.py --refresh    # force a rescan even if cached
    python setup_paths.py --forget     # delete the cache

Exit codes: 0 = paths ready, 2 = nothing usable found (message says why).
Stdlib only; no CarSim products are launched or modified (read-only checks).
"""
import argparse
import json
import os
import shutil
import string
import sys
import time
from pathlib import Path

from vehicle_registry import sha256

CONFIG_ENV = "CARSIM_GUIDE_CONFIG"
CONFIG_DEFAULT = Path.home() / ".carsim_guide_paths.json"

CLI_NAME = "VS_SolverWrapper_CLI_64.exe"
DLL_NAME = "carsim_64.dll"
PROG_SUFFIX = "_prog"      # case-insensitive match on directory names
DATA_SUFFIX = "_data"
MAX_OTHER_BASES = 8

WHAT = ("prog", "datadir", "cli_solver", "solver_dll", "license_manager",
        "base_run_all", "other_bases", "matlab")


def config_path():
    return Path(os.environ.get(CONFIG_ENV, str(CONFIG_DEFAULT)))


def load_config():
    """Return the cached config dict, or None if absent/corrupt."""
    try:
        cfg = json.loads(config_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return cfg if isinstance(cfg, dict) and cfg.get("prog") else None


def save_config(cfg):
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# discovery (read-only filesystem checks)
# ---------------------------------------------------------------------------
def _verifies_as_prog(d):
    """A real install root has both the CLI solver wrapper and the 64-bit DLL."""
    return ((d / "Programs" / CLI_NAME).is_file()
            and (d / "Programs" / "solvers" / DLL_NAME).is_file())


def default_search_dirs():
    """Standard install parents to scan (depth 1, so this stays fast)."""
    roots = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive = "%s:\\" % letter
            if os.path.exists(drive):
                roots += [drive, drive + "Program Files",
                          drive + "Program Files (x86)"]
    else:
        roots = ["/opt", "/usr/local", str(Path.home())]
    return roots


def prog_candidates(search_dirs=None):
    """CarSim*_Prog directories that verify as install roots (CLI + DLL)."""
    found = []
    for root in (search_dirs if search_dirs is not None
                 else default_search_dirs()):
        try:
            entries = list(os.scandir(root))
        except OSError:
            continue
        for e in entries:
            name = e.name.lower()
            if (e.is_dir() and name.startswith("carsim")
                    and name.endswith(PROG_SUFFIX)
                    and _verifies_as_prog(Path(e.path))):
                found.append(Path(e.path))
    # dedupe, keep scan order (drive order = stable)
    return list(dict.fromkeys(found))


def datadir_candidates(prog):
    """The matching *_Data sibling first, then any other CarSim*_Data copy."""
    parent, wanted = prog.parent, prog.name.lower().replace(PROG_SUFFIX,
                                                            DATA_SUFFIX)
    primary = others = None
    try:
        entries = sorted(e.name for e in parent.iterdir()
                         if e.is_dir() and e.name.lower().startswith("carsim")
                         and DATA_SUFFIX in e.name.lower())
    except OSError:
        entries = []
    rest = [n for n in entries if n.lower() != wanted]
    if wanted in (n.lower() for n in entries):
        primary = parent / next(n for n in entries if n.lower() == wanted)
    if rest:
        others = [parent / n for n in rest]
    return primary, others or []


def find_bases(datadirs):
    """GUI-expanded Run_all.par files under <datadir>/Results/Run_*, newest first."""
    bases = []
    for dd in datadirs:
        for p in sorted(dd.glob("Results/Run_*/Run_all.par")):
            try:
                mtime = p.stat().st_mtime
            except OSError:
                continue
            bases.append((mtime, p))
    bases.sort(reverse=True)
    return [str(p.resolve()) for _, p in bases]


def _derive_from_prog(prog):
    cli = str(prog / "Programs" / CLI_NAME)
    dll = str(prog / "Programs" / "solvers" / DLL_NAME)
    cslm = str(prog / "Programs" / "cslm.exe")
    return cli, dll, (cslm if (prog / "Programs" / "cslm.exe").is_file()
                      else None)


def discover(search_dirs=None):
    """Scan and return a full config dict; raise SystemExit if no install."""
    progs = prog_candidates(search_dirs)
    if not progs:
        raise SystemExit(
            "no CarSim install found under standard locations (looked for a\n"
            "CarSim*_Prog directory containing Programs/%s and\n"
            "Programs/solvers/%s).\n"
            "Install CarSim, or point at it manually:\n"
            "  python setup_paths.py --set prog=\"<path to CarSim*_Prog>\""
            % (CLI_NAME, DLL_NAME))
    prog = progs[0]
    cli, dll, cslm = _derive_from_prog(prog)
    primary_data, other_datas = datadir_candidates(prog)
    all_datas = ([primary_data] if primary_data else []) + other_datas
    bases = find_bases(all_datas)
    return {
        "prog": str(prog.resolve()),
        "datadir": str(primary_data.resolve()) if primary_data
        else (str(other_datas[0].resolve()) if other_datas else None),
        "other_datadirs": [str(d.resolve()) for d in other_datas],
        "cli_solver": cli,
        "solver_dll": dll,
        "license_manager": cslm,
        "base_run_all": None,
        "other_bases": bases[:MAX_OTHER_BASES],
        "matlab": shutil.which("matlab"),   # optional: Simulink co-sim examples
        "discovered_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                        time.gmtime()),
    }


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def _validate(cfg):
    """All four runtime paths are required, even when absent from the cache."""
    problems = [k for k in ("prog", "datadir", "cli_solver", "solver_dll")
                if not cfg.get(k) or not (Path(cfg[k]).is_dir() if k in ("prog", "datadir")
                                          else Path(cfg[k]).is_file())]
    for k in problems:
        print("warning: cached %s missing or invalid: %s" % (k, cfg.get(k)),
              file=sys.stderr)
    return not problems


def _apply_set(cfg, pairs):
    """Manual key=value overrides; re-derive everything downstream of prog."""
    allowed = {"prog", "datadir", "base_run_all", "matlab"}
    for pair in pairs:
        if "=" not in pair:
            raise SystemExit("--set expects key=\"value\" pairs, got %r" % pair)
        k, v = (s.strip() for s in pair.split("=", 1))
        if k not in allowed or not v:
            raise SystemExit("--set keys: %s" % ", ".join(sorted(allowed)))
        cfg[k] = str(Path(v).resolve())
        if k == "base_run_all":
            cfg["base_sha256"] = sha256(cfg[k])
            cfg["base_selection"] = "explicit"
    if cfg.get("prog"):
        prog = Path(cfg["prog"])
        cfg["cli_solver"], cfg["solver_dll"], cfg["license_manager"] = \
            _derive_from_prog(prog)
        if not cfg.get("datadir"):
            primary, others = datadir_candidates(prog)
            if primary or others:
                cfg["datadir"] = str((primary or others[0]).resolve())
                cfg["other_datadirs"] = [str(d.resolve()) for d in others]
    if cfg.get("datadir") and not cfg.get("base_run_all"):
        bases = find_bases([Path(cfg["datadir"])])
        cfg["other_bases"] = bases[:MAX_OTHER_BASES]
    missing = [k for k in ("prog", "datadir") if not cfg.get(k)]
    if missing:
        raise SystemExit("still missing %s after --set" % ", ".join(missing))
    return cfg


def _resolved_line(cfg):
    keys = ("prog", "datadir", "base_run_all")
    return json.dumps({k: cfg.get(k) for k in keys}, separators=(",", ":"))


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Discover and cache CarSim install paths (first run on a "
                    "machine); later runs print the cache in milliseconds.")
    ap.add_argument("--json", action="store_true",
                    help="print {prog,datadir,base_run_all} as one JSON line")
    ap.add_argument("--set", metavar="KEY=\"VALUE\"", nargs="+", default=[],
                    help="manual override: prog= / datadir= / base_run_all=")
    ap.add_argument("--refresh", action="store_true",
                    help="rescan even if a cache already exists")
    ap.add_argument("--forget", action="store_true",
                    help="delete the cached config and exit")
    args = ap.parse_args(argv)

    if args.forget:
        p = config_path()
        p.unlink(missing_ok=True)
        print("deleted %s" % p)
        return 0

    old = load_config()
    cfg = None if args.refresh else old
    if cfg is None:
        try:
            cfg = discover()
        except SystemExit:
            if not args.set:
                raise
            cfg = {}  # --set can bootstrap a non-standard install by hand
    elif not args.set and not _validate(cfg):
        print("cache stale - rediscovering", file=sys.stderr)
        cfg = discover()
    if old and old.get("base_selection") == "explicit" and not cfg.get("base_run_all"):
        for key in ("base_run_all", "base_sha256", "base_selection"):
            cfg[key] = old.get(key)
    if args.set:
        cfg = _apply_set(cfg, args.set)
    if not _validate(cfg):
        raise SystemExit("Runtime paths incomplete; set prog/datadir explicitly")
    if cfg.get("base_selection") != "explicit":
        cfg["base_run_all"] = None  # migrate legacy newest-base caches
    if cfg.get("base_run_all"):
        base = Path(cfg["base_run_all"])
        if not base.is_file() or sha256(base) != cfg.get("base_sha256"):
            raise SystemExit("Pinned base missing or changed; explicitly rebind base_run_all")
    save_config(cfg)

    if not cfg.get("base_run_all"):
        print("note: select a GUI-expanded base explicitly with "
              "--set base_run_all=\"...\"; other_bases are candidates only", file=sys.stderr)
    if args.json:
        print(_resolved_line(cfg))
    else:
        print("CarSim paths ready (cached to %s):" % config_path())
        for k in WHAT:
            print("  %-16s %s" % (k, cfg.get(k)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
