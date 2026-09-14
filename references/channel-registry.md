# Channel and unit registry (core)

`scripts/result_contract.py:CHANNEL_REGISTRY` is the authoritative executable
mapping. Each explicit CSV name has native unit, SI unit, conversion factor and
a category. Unknown names fail closed — units are never guessed. No prefix
matching is used for reading.

| Channels | Native → SI | Category |
|---|---|---|
| Time | s → s | time |
| Vx, Vy (and registered Vx corners) | km/h → m/s, /3.6 | vehicle_state |
| Ax, Ay | g → m/s^2, ×9.80665 | vehicle_state |
| AVz | deg/s → rad/s, ×π/180 | vehicle_state |
| Roll, Pitch, Yaw | deg → rad, ×π/180 | vehicle_state |
| Xo, Yo, Zo | m → m | vehicle_state |
| Station | m → m | road |
| Vx at four corners | km/h → m/s, /3.6 | wheel |
| AVy at four corners | rpm → rad/s, ×2π/60 | wheel |
| Steer at four corners | deg → rad, ×π/180 | steering |
| My_Dr at four corners | N*m → N*m | powertrain |
| My_Bk at four corners | N*m → N*m | control |
| AV_Mt_D1_L/R, D2_L/R | rpm → rad/s, ×2π/60 | powertrain |
| Fx, Fy, Fz at four corners | N → N | tire |
| Kappa at four corners | dimensionless | tire |
| Alpha at four corners | deg → rad, ×π/180 | tire |

Tire outputs (Fx/Fy/Fz/Kappa/Alpha) are ordinary CarSim simulation output
variables: core readers return them like any other channel. Whether they may
feed an estimator or learning algorithm is workflow-specific — the optional
research workflows mark them as privileged simulator information (`role` in
the registry); see
[workflows/estimator-validation.md](workflows/estimator-validation.md).

Corners are L1/FL, R1/FR, L2/RL, R2/RR. WRT `ROLL`/`PITCH` map to CSV
`Roll`/`Pitch`. `Lat_Veh` and `Lat_Targ` are excluded as unreliable
(up to 15 m drift; derive lateral position from `Yo`/`Yaw`).

The contract is for native CarSim CSV output under the documented setup, not
arbitrary user-converted exports or Simulink export arrays. Check channel units
when changing a vehicle, solver release or unit configuration. Standard gravity
9.80665 replaces the old rounded 9.81 conversion; existing results change slightly.

`carsim_batch.read_run_csv(path, columns, units)` is the core reader:
`units="SI"` (default) or `units="native"` for raw CarSim values. The
workflow-layer helpers live in the same module but are not part of the core
contract: `RunData.estimator_view()` returns a copy and checks the workflow
`role` and whitelist membership; `GroundTruthLeakageError` blocks
intrinsically privileged requests from estimator code. This is an
accidental-leakage guard within the workflow API, not a security sandbox
preventing direct access to the original CSV.
