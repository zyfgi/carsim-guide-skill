# Channel and unit registry

`scripts/result_contract.py:CHANNEL_REGISTRY` is the authoritative executable
mapping. Each explicit CSV name has native unit, SI unit, conversion factor,
role and source. Unknown names fail closed. No prefix guessing is used for reading.

| Channels | Native → SI | Role |
|---|---|---|
| Time | s → s | time |
| Vx, Vy (and registered Vx corners) | km/h → m/s, /3.6 | sensor-eligible |
| Ax, Ay | g → m/s^2, ×9.80665 | sensor-eligible |
| AVz | deg/s → rad/s, ×π/180 | sensor-eligible |
| Roll, Pitch, Yaw, Steer at four corners | deg → rad, ×π/180 | sensor-eligible |
| AVy at four corners; AV_Mt_D1_L/R, D2_L/R | rpm → rad/s, ×2π/60 | sensor-eligible |
| My_Dr, My_Bk at four corners | N*m → N*m | sensor-eligible |
| Xo, Yo, Zo, Station | m → m | sensor-eligible |
| Fx, Fy, Fz at four corners | N → N | truth |
| Kappa at four corners | dimensionless | truth |
| Alpha at four corners | deg → rad, ×π/180 | truth |

Corners are L1/FL, R1/FR, L2/RL, R2/RR. WRT `ROLL`/`PITCH` map to CSV
`Roll`/`Pitch`. `Lat_Veh` and `Lat_Targ` are excluded as unreliable.

The contract is for native CarSim CSV output under the documented setup, not
arbitrary user-converted exports or Simulink export arrays. Check channel units
when changing a vehicle, solver release or unit configuration. Standard gravity
9.80665 replaces the old rounded 9.81 conversion; existing results change slightly.

Sensor-eligible is a candidate, not a hardware assertion. `Vy`, exact wheel torque,
wheel steer and attitude may be unavailable on the actual vehicle. The experiment
whitelist controls which candidates the estimator sees. Non-whitelisted channels
are placed in the evaluation partition, even when not intrinsically truth-only.

`RunData.estimator_view()` returns a copy and checks role and membership.
`GroundTruthLeakageError` blocks intrinsically truth-only requests; missing or
excluded sensor channels also raise. This is an accidental-leakage guard within
the API, not a security sandbox preventing direct access to the original CSV.
