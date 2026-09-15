# Control mode selection

Control semantics and coupling are separate. Never treat a target as a direct
actuator command, or prerecorded replay as closed loop.

| Mode | CLI batch | Simulink | VS API | Runtime feedback |
|---|---:|---:|---:|---:|
| `driver_internal` | yes | optional | optional | internal only |
| `predefined_table` | yes | optional | optional | no |
| `imported_signal` | yes | yes | yes | no when prerecorded |
| `simulink_external` | no | yes | no | yes |
| `vs_api_external` | no | no | yes | yes |

Use `ControlSpec` with one semantic: `speed_target`, `throttle_command`,
`brake_command`, `steering_target`, `steering_wheel_angle`,
`road_wheel_angle`, or `wheel_torque_command`.

Choose CLI batch for inputs fixed before the run. Choose Simulink when control
depends on current outputs. Choose VS API only when low-level stepping is
required and Simulink is unsuitable.

The VS API route is a documented prototype and remains unverified end-to-end.
See `references/compatibility.md` for verified environments.
