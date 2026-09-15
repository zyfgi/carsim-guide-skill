# Advanced controls (open-loop driver inputs, torque imports, table semantics)

Use these CarSim 2024.0 control forms for open-loop acceleration/braking and
per-wheel torque control. Confirm actuator availability and limits in the
selected Run Control base.

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
- Inject via `unsafe_extra_lines` AFTER the generated speed lines — last-write-wins flips `OPT_SC 1` to `0` cleanly.

## 2. Per-wheel torque import (torque vectoring / TCS)

The 4-motor EV accepts per-wheel torque commands (N·m, delivered 1:1 at the wheels — verified: `My_Dr_*` tracks the command exactly). **Form matters, and it is not the documented textual form:**

```
IMPORT IMP_M_MOTOR_CMD_D1_L Add 0.0! 1     <-- GUI-native ACTIVE form (verified)
IMPORT IMP_M_MOTOR_CMD_D1_R Add 0.0! 1
IMPORT IMP_M_MOTOR_CMD_D2_L Add 0.0! 1
IMPORT IMP_M_MOTOR_CMD_D2_R Add 0.0! 1
PORTS_IMP 1,4
```

- With active ports, use the GUI-native `Add 0.0! 1` form shown above;
  `VS_REPLACE <val>` does not activate the live signal.
- **Constant torque without Simulink**: declare `IMPORT ... VS_REPLACE <value>`
  with `PORTS_IMP 0`; imports hold their initial values for a plain CLI run.
- **Time-varying torque control**: use Simulink co-simulation with
  `references/simulink-cosim.md`, `scripts/tv_cosim.m`, and
  `examples/torque_vectoring.py`. Respect the per-wheel motor limits defined by
  the selected vehicle.

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
- **Property/geometry tables inside subsystem datasets (spring/damper/kinematics/aero maps) are NOT verified via override** — the append behavior documented for LTARG makes them risky. For design-space sweeps over geometry: edit the dataset in the GUI (or MCP `set_table` on a clone) and re-expand the base, once per design point. Scalars (`M_SU`, gear ratios, etc.) remain clean `unsafe_extra_lines` territory.

## 4. Operational notes

- **Acceleration**: `OPT_SC 0` plus constant torque import (`PORTS_IMP 0`,
  section 2); measure distance from `Xo`.
- **Braking**: use the open-loop brake table in section 1. Achievable
  deceleration depends on the selected vehicle's brake configuration.
- **Skidpad**: constant SW angle (open-loop steering) + closed-loop speed traces a steady circle — measure radius/lateral accel from `Yo/Yaw`.
- **Torque vectoring / TCS**: use section 2. Slip signals (`Kappa_*`) are
  already in the WRT whitelist; exclude the initial standing-start
  normalization spike where appropriate.
