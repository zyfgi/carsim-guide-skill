# Control mode selection

Control semantics and coupling are separate. Never treat a target as a direct
actuator command, or prerecorded replay as closed loop.

| Mode | CLI batch | Simulink | VS API | Runtime feedback | Verification |
|---|---:|---:|---:|---:|---|
| `driver_internal` | yes | optional | optional | internal only | 2024.0 field-tested |
| `predefined_table` | yes | optional | optional | no | 2024.0 field-tested |
| `imported_signal` | yes | yes | yes | no when prerecorded | 2024.0 torque-import pattern field-tested |
| `simulink_external` | no | yes | no | yes | 2024.0 field-tested |
| `vs_api_external` | no | no | yes | yes | interface prototype; end-to-end unverified |

Use `ControlSpec` with one semantic: `speed_target`, `throttle_command`,
`brake_command`, `steering_target`, `steering_wheel_angle`,
`road_wheel_angle`, or `wheel_torque_command`.

Choose CLI batch for inputs fixed before the run. Choose Simulink when control
depends on current outputs. Choose VS API only when low-level stepping is
required and Simulink is unsuitable.
