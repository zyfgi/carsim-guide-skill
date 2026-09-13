# Advanced controls (open-loop driver inputs, torque imports, table semantics)

Field-verified recipes that unlock event-style scenarios (FSAE-style acceleration/braking) and per-wheel torque control (torque vectoring / TCS). Everything below ran on the 4-motor EV base; keywords were cross-checked against official database runs.

## 1. Open-loop driver controls (`OPT_SC 0`)

The closed-loop speed controller (`OPT_SC 1`) caps acceleration at the controller's authority. For event-style runs, switch to open loop:

```
OPT_SC 0                       ! speed controller OFF (echo: "0 -> Off (open-loop)")
THROTTLE_ENGINE_TABLE LINEAR_FLAT   ! rows: time s, pedal 0..1 (works for EVs too)
0, 1
6, 1
ENDTABLE
PBK_CON_TABLE LINEAR_FLAT      ! rows: time s, master-cylinder pressure MPa
0, 0
6.2, 0
6.5, 15.0
ENDTABLE
```

**Critical semantics** (all verified):

- With `OPT_SC 0` the vehicle starts **from standstill** — the speed table's first row no longer sets the initial speed. To test braking from speed, accelerate first in the same run (throttle table), then apply the brake table.
- `PBK_CON` is **MPa at the master cylinder**; ~2 MPa is gentle, this vehicle saturates by ~10 MPa.
- Inject via `extra_lines` AFTER the generated speed lines — last-write-wins flips `OPT_SC 1` to `0` cleanly.

## 2. Per-wheel torque import (torque vectoring / TCS)

The 4-motor EV accepts per-wheel torque commands (N·m, delivered 1:1 at the wheels — verified: `My_Dr_*` tracks the command exactly). **Form matters, and it is not the documented textual form:**

```
IMPORT IMP_M_MOTOR_CMD_D1_L Add 0.0! 1     <-- GUI-native ACTIVE form (verified)
IMPORT IMP_M_MOTOR_CMD_D1_R Add 0.0! 1
IMPORT IMP_M_MOTOR_CMD_D2_L Add 0.0! 1
IMPORT IMP_M_MOTOR_CMD_D2_R Add 0.0! 1
PORTS_IMP 1,4
```

- `VS_REPLACE <val>` parses and is accepted, but with ports ACTIVE it stayed **inert** in testing (car never moved) — do not waste an hour on it. The `Add 0.0! 1` form comes verbatim from the official torque-vectoring run control and works.
- **Constant torque without Simulink**: declare `IMPORT ... VS_REPLACE 150` with `PORTS_IMP 0` — imports hold their initial values, giving a fixed per-wheel torque in a plain CLI run (verified: My_Dr = 149 N·m, Ax = 1.83 m/s² vs theory 1.66). This is the zero-dependency FSAE acceleration-event pattern.
- **Time-varying torque control**: Simulink co-sim (`references/simulink-cosim.md` + `scripts/tv_cosim.m` + `examples/torque_vectoring.py`). Verified demo: speed PI on total torque + yaw PI on the left/right differential, steering wheel held at exactly 0.000° — yaw target 0.06 rad/s reached within 4.3% error. Mind the saturation budget: per-wheel ±580 N·m (motor limit) bounds the achievable differential torque, which bounds the zero-steer yaw rate (0.1 rad/s target did NOT converge at 50 km/h; 0.06 did).

## 3. Table-override semantics (echo-verified)

Does a same-name table in override.par replace or append? Verified by reading `run_echo.par` after a run with distinctive rows:

| Table | Semantics | Evidence |
|---|---|---|
| `SPEED_TARGET_TABLE` | **REPLACE** | echo contains exactly the override's rows |
| `STEER_SW_TABLE` | **REPLACE** | echo contains exactly the override's rows |
| `MU_ROAD_CARPET` | **REPLACE** | echo (as `MU_ROAD_CARPET(1)`) contains exactly the override's rows |
| `LTARG_TABLE` (path follower) | **APPEND** (trap) | rows concatenate with the base's table — the documented phantom-target trap |

Notes:

- A **constant-valued** speed table is auto-normalized to `SPEED_TARGET_CONSTANT` in the echo — the table "disappearing" from the echo is normal, not a failure.
- Echo keywords may carry an index suffix (`MU_ROAD_CARPET(1)`) — grep accordingly.
- **Property/geometry tables inside subsystem datasets (spring/damper/kinematics/aero maps) are NOT verified via override** — the append behavior documented for LTARG makes them risky. For design-space sweeps over geometry: edit the dataset in the GUI (or MCP `set_table` on a clone) and re-expand the base, once per design point. Scalars (`M_SU`, gear ratios, etc.) remain clean `extra_lines` territory.

## 4. FSAE-oriented notes

- **Acceleration event**: `OPT_SC 0` + constant torque import (`PORTS_IMP 0`, §2) — measure 75 m time from `Xo`.
- **Braking test (rule: ≥ 0.7 g)**: open-loop brake table, §1. Mechanism verified; note the achievable decel is vehicle-hardware-limited — this street-EV base saturates at ~0.64 g because its brake config only actuates the front axle (rear `My_Bk_*` = 0, fronts lock at kappa = −1). An FSAE base with 4-wheel brakes will clear 0.7 g.
- **Skidpad**: constant SW angle (open-loop steering) + closed-loop speed traces a steady circle — measure radius/lateral accel from `Yo/Yaw`.
- **Torque vectoring / TCS**: §2; slip signals (`Kappa_*`) are already in the WRT whitelist (exclude t < 0.5 s after a standing start — normalization spike).
