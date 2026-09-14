#!/usr/bin/env python3
"""Runnable example: torque-vectoring co-simulation (4-motor EV, zero steer).

Generates a co-sim simfile with FOUR per-wheel motor-torque imports
(IMP_M_MOTOR_CMD_*) and four exports, then runs scripts/tv_cosim.m headless:
speed is held by a PI on total wheel torque, and a yaw-rate target is reached
PURELY by left/right torque vectoring (steering wheel stays at zero).
Verifies the yaw tracking in pandas.

Usage:
  python examples/torque_vectoring.py \
      --prog    "C:/CarSim/CarSim2024.0_Prog" \
      --datadir "C:/CarSim/CarSim2024.0_Data" \
      --base    "C:/work/base/Run_all.par" \
      --out     "C:/work/tv_demo" \
      --matlab  "C:/MATLAB/R2025b/bin/matlab.exe"
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

logger = logging.getLogger("torque_vectoring")

EXTRA_LINES = [
    # per-wheel motor torque commands, N.m at the wheels (verified 1:1 with
    # the My_Dr_* output channels); EXACT form of the official torque-vectoring
    # run control ("Add 0.0! 1" = GUI-native active form)
    "IMPORT IMP_M_MOTOR_CMD_D1_L Add 0.0! 1",
    "IMPORT IMP_M_MOTOR_CMD_D1_R Add 0.0! 1",
    "IMPORT IMP_M_MOTOR_CMD_D2_L Add 0.0! 1",
    "IMPORT IMP_M_MOTOR_CMD_D2_R Add 0.0! 1",
    "EXPORT Vx",        # km/h
    "EXPORT AVz",       # deg/s
    "EXPORT Yo",        # m
    "EXPORT Steer_SW",  # deg (stays 0 -- yaw comes from torque vectoring)
    "PORTS_IMP 1,4",    # <array #>,<count> -- never a single count
    "PORTS_EXP 1,4",
]
TARGET_DEGS = 0.06 / 0.0174533


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prog", default=None,
                    help="CarSim *_Prog dir (default: setup_paths.py cache)")
    ap.add_argument("--datadir", default=None,
                    help="CarSim *_Data dir (default: setup_paths.py cache)")
    ap.add_argument("--base", default=None,
                    help="GUI-expanded Run_all.par (default: cache)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--matlab", default=None,
                    help="path to matlab.exe (default: setup_paths.py cache)")
    ap.add_argument("--tstop", type=float, default=30.0)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    args.prog, args.datadir, args.base = cb.resolve_paths(
        args.prog, args.datadir, args.base)
    args.matlab = args.matlab or cb.cached_paths().get("matlab")
    if not args.matlab:
        ap.error("--matlab not given and none in the setup_paths.py cache "
                 "(run setup_paths.py with MATLAB on PATH)")
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    os.makedirs(args.out, exist_ok=True)
    # OPT_SC 0: open loop (torque imports are the only drive); initial speed
    # from standstill, built up by the speed PI itself
    open(os.path.join(args.out, "override.par"), "w", newline="\n").write(
        cb.override_par(args.base, args.tstop,
                        [(0, 0), (args.tstop, 0)],
                        [(0, 0), (args.tstop, 0)],
                        extra_lines=EXTRA_LINES + ["OPT_SC 0"]))
    sim = cb.simfile(args.out, args.prog, args.datadir)
    sim = sim.replace("PORTS_IMP 0", "PORTS_IMP 1,4")
    sim = sim.replace("PORTS_EXP 0", "PORTS_EXP 1,4")
    open(os.path.join(args.out, "simfile.sim"), "w", newline="\n").write(sim)
    logger.info("co-sim inputs written to %s", args.out)

    solver_matlab = os.path.join(args.prog, "Programs", "solvers", "Matlab")
    scripts_dir = os.path.dirname(cb.__file__)
    cmd = [args.matlab, "-batch",
           "addpath('%s'); addpath('%s'); tv_cosim('%s', '%s')"
           % (solver_matlab.replace("\\", "/"), scripts_dir.replace("\\", "/"),
              args.out.replace("\\", "/"), solver_matlab.replace("\\", "/"))]
    logger.info("launching MATLAB ...")
    proc = subprocess.run(cmd, capture_output=True, text=True,
                          timeout=900, encoding="utf-8", errors="replace")
    tail = "\n".join((proc.stdout or "").splitlines()[-6:])
    logger.info("MATLAB tail:\n%s", tail)
    if proc.returncode != 0 or "DONE" not in (proc.stdout or ""):
        raise RuntimeError("MATLAB co-sim failed (see tail above)")

    df = pd.read_csv(os.path.join(args.out, "cosim_results.csv"),
                     names=["t", "vx_kmh", "avz_degs", "yo_m",
                            "steersw_deg", "tl", "tr"])
    w = df[df.t.between(args.tstop / 2, args.tstop)]
    err = abs(w.avz_degs.mean() - TARGET_DEGS) / TARGET_DEGS * 100
    print("steady: AVz = %.3f deg/s (target %.3f) -> error %.2f%%"
          % (w.avz_degs.mean(), TARGET_DEGS, err))
    print("Vx = %.2f km/h | Steer_SW = %.3f deg | T_L = %.0f, T_R = %.0f N.m"
          % (w.vx_kmh.mean(), w.steersw_deg.max(), w.tl.mean(), w.tr.mean()))
    if not (err < 5.0 and w.steersw_deg.abs().max() < 1e-6
            and w.vx_kmh.mean() > 40):
        raise SystemExit("FAIL: torque-vectoring yaw not achieved")
    print("PASS: yaw generated purely by torque vectoring at zero steering")


if __name__ == "__main__":
    sys.exit(main())
