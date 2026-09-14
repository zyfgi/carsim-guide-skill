#!/usr/bin/env python3
"""Runnable example: batch parameter sweep with the carsim-guide workflow.

Sweeps road friction (and optionally a central payload) over the same
speed/steer schedule, runs every variant headless, and writes a one-row-per-
variant summary CSV (SI units) plus each run's artifacts in its own folder.

Usage:
  python examples/param_sweep.py \
      --prog    "C:/CarSim/CarSim2024.0_Prog" \
      --datadir "C:/CarSim/CarSim2024.0_Data" \
      --base    "C:/work/base/Run_all.par" \
      --out     "C:/work/friction_sweep"

Requires: CarSim 2024.0 with license (GUI open or cslm.exe), Python 3 + pandas.
"""
import argparse
import logging
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "scripts"))
import carsim_batch as cb  # noqa: E402
from scenario_schema import VehicleOverrides  # noqa: E402

logger = logging.getLogger("param_sweep")


def main():
    ap = argparse.ArgumentParser(description="friction/payload sweep demo")
    ap.add_argument("--prog", default=None,
                    help="CarSim *_Prog dir (default: setup_paths.py cache)")
    ap.add_argument("--datadir", default=None,
                    help="CarSim *_Data dir (default: setup_paths.py cache)")
    ap.add_argument("--base", default=None, help="GUI-expanded Run_all.par "
                    "(default: setup_paths.py cache)")
    ap.add_argument("--out", required=True, help="sweep root directory")
    ap.add_argument("--mus", default="0.4,0.6,0.9",
                    help="comma-separated friction values (default 0.4,0.6,0.9)")
    ap.add_argument("--payload-kg", type=float, default=0.0,
                    help="optional central sprung-mass addition (default 0)")
    ap.add_argument("--base-sprung-mass-kg", type=float,
                    help="verified base sprung mass, required when adding payload")
    ap.add_argument("--tstop", type=float, default=30.0)
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    args.prog, args.datadir, args.base = cb.resolve_paths(
        args.prog, args.datadir, args.base)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")

    speed_rows = [(0, 43), (args.tstop / 2, 65), (args.tstop, 50)]  # s, km/h
    steer_rows = [(0, 0), (args.tstop / 3, 9),                      # s, deg
                  (2 * args.tstop / 3, -9), (args.tstop, 0)]
    vehicle_overrides = None
    if args.payload_kg:
        if args.base_sprung_mass_kg is None:
            ap.error("--payload-kg requires verified --base-sprung-mass-kg")
        vehicle_overrides = VehicleOverrides(sprung_mass_kg=args.base_sprung_mass_kg + args.payload_kg)

    rows = []
    for mu in [float(m) for m in args.mus.split(",")]:
        tag = "mu%02d" % round(mu * 100)
        d = os.path.join(args.out, tag)
        sim = cb.make_scenario(d, args.base, args.prog, args.datadir,
                               args.tstop, speed_rows, steer_rows,
                               mu=mu, vehicle_overrides=vehicle_overrides,
                               outputs=cb.OUTPUTS_CORE + cb.OUTPUTS_EXTRA)
        logger.info("running %s ...", tag)
        cb.run_solver(sim, args.prog, timeout=args.timeout)
        df = cb.read_run_csv(os.path.join(d, "run.csv"),
                             columns=["Time", "Vx", "Ax", "Ay", "AVz",
                                      "Kappa_L1", "Kappa_R1",
                                      "Kappa_L2", "Kappa_R2"])
        rolling = df[df.Time > 0.5]  # skip the standing-start Kappa spike
        rows.append({
            "mu": mu,
            "payload_extra_kg": args.payload_kg,
            "ax_max_mps2": rolling.Ax.max(),
            "ay_max_mps2": rolling.Ay.abs().max(),
            "yaw_rate_max_radps": rolling.AVz.abs().max(),
            "kappa_max": rolling[["Kappa_L1", "Kappa_R1",
                                  "Kappa_L2", "Kappa_R2"]].abs().max().max(),
        })
        logger.info("%s done: ax_max=%.2f kappa_max=%.4f",
                    tag, rows[-1]["ax_max_mps2"], rows[-1]["kappa_max"])

    import pandas as pd
    summary = os.path.join(args.out, "sweep_summary.csv")
    pd.DataFrame(rows).to_csv(summary, index=False)
    logger.info("summary -> %s", summary)
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    sys.exit(main())
