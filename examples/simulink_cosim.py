#!/usr/bin/env python3
"""Runnable example: Simulink + CarSim closed-loop co-simulation, end to end.

Generates a co-sim simfile (steering import + 5 exports) with the normal
override workflow, builds & runs a Simulink PI yaw-rate controller around the
CarSim S-Function headless via `matlab -batch`, then verifies the tracking in
pandas. This is the demo behind references/simulink-cosim.md (verified:
0.00% steady-state error).

Usage:
  python examples/simulink_cosim.py \
      --prog    "C:/CarSim/CarSim2024.0_Prog" \
      --datadir "C:/CarSim/CarSim2024.0_Data" \
      --base    "C:/work/base/Run_all.par" \
      --out     "C:/work/cosim_demo" \
      --matlab  "C:/MATLAB/R2025b/bin/matlab.exe"

Requires: CarSim 2024.0 with license (GUI or cslm.exe), MATLAB R2023a+ with
Simulink, Python 3 + pandas.
"""
import argparse
import logging
import os
import subprocess
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import carsim_batch as cb  # noqa: E402
import pandas as pd  # noqa: E402

logger = logging.getLogger("simulink_cosim")

EXTRA_LINES = [
    "IMPORT IMP_STEER_SW REPLACE",  # steering wheel angle [deg] from Simulink
    "EXPORT Vx",                     # export order = declaration order
    "EXPORT AVz",                    # [deg/s] -> element 2 (feedback signal)
    "EXPORT Ay",                     # [g]
    "EXPORT Yo",                     # [m]
    "EXPORT Steer_SW",               # [deg]
    "PORTS_IMP 1,1",                 # <array #>,<count> -- never a single count
    "PORTS_EXP 1,5",
]
TARGET_DEGS = 0.15 / 0.0174533  # 0.15 rad/s expressed in deg/s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prog", required=True, help="CarSim *_Prog directory")
    ap.add_argument("--datadir", required=True, help="CarSim *_Data directory")
    ap.add_argument("--base", required=True, help="GUI-expanded Run_all.par")
    ap.add_argument("--out", required=True, help="work/output directory")
    ap.add_argument("--matlab", required=True, help="path to matlab.exe")
    ap.add_argument("--tstop", type=float, default=30.0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    # 1) co-sim inputs via the normal override workflow
    os.makedirs(args.out, exist_ok=True)
    open(os.path.join(args.out, "override.par"), "w", newline="\n").write(
        cb.override_par(args.base, args.tstop,
                        [(0, 50), (args.tstop, 50)],
                        [(0, 0), (args.tstop, 0)],
                        extra_lines=EXTRA_LINES))
    sim = cb.simfile(args.out, args.prog, args.datadir)
    sim = sim.replace("PORTS_IMP 0", "PORTS_IMP 1,1")
    sim = sim.replace("PORTS_EXP 0", "PORTS_EXP 1,5")
    open(os.path.join(args.out, "simfile.sim"), "w", newline="\n").write(sim)
    logger.info("co-sim inputs written to %s", args.out)

    # 2) build + run the Simulink model headless
    solver_matlab = os.path.join(args.prog, "Programs", "solvers", "Matlab")
    scripts_dir = os.path.dirname(cb.__file__)
    cmd = [args.matlab, "-batch",
           "addpath('%s'); addpath('%s'); cosim_model('%s', '%s')"
           % (solver_matlab.replace("\\", "/"), scripts_dir.replace("\\", "/"),
              args.out.replace("\\", "/"), solver_matlab.replace("\\", "/"))]
    logger.info("launching MATLAB ...")
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=900, encoding="utf-8", errors="replace")
    tail = "\n".join((proc.stdout or "").splitlines()[-6:])
    logger.info("MATLAB tail:\n%s", tail)
    if proc.returncode != 0 or "DONE" not in (proc.stdout or ""):
        raise RuntimeError("MATLAB co-sim failed (see tail above)")

    # 3) verify in pandas (exports are in NATIVE CarSim units)
    df = pd.read_csv(os.path.join(args.out, "cosim_results.csv"),
                     names=["t", "vx_kmh", "avz_degs", "ay_g", "yo_m",
                            "steersw_deg", "steer_cmd_deg"])
    w = df[df.t.between(args.tstop / 3, args.tstop)]
    err = abs(w.avz_degs.mean() - TARGET_DEGS) / TARGET_DEGS * 100
    print("steady AVz = %.3f deg/s (target %.3f) -> error %.2f%%"
          % (w.avz_degs.mean(), TARGET_DEGS, err))
    print("Vx = %.2f km/h | steer = %.2f deg" % (w.vx_kmh.mean(),
                                                 w.steer_cmd_deg.mean()))
    if err >= 2.0:
        raise SystemExit("FAIL: tracking error %.2f%% >= 2%%" % err)
    print("PASS: Simulink+CarSim closed loop verified")


if __name__ == "__main__":
    sys.exit(main())
