# Capability status

Status is evidence-specific. “Implemented” is not a synonym for “verified in
licensed CarSim,” and a fresh-agent behavior pass is a separate claim again.

| Capability | Implemented | Unit-tested | Licensed CarSim-tested | Fresh-agent behavior-tested |
|---|---:|---:|---:|---:|
| Multilingual output query normalization | yes | yes | not applicable (read-only discovery) | pass, P2.1 A |
| Evidence-bearing output artifact candidates | yes | yes | not applicable (read-only discovery) | pass, P2.1 A |
| Multilingual parameter discovery / ambiguity | yes | yes | not claimed | pass, P2.1 B/C |
| DATADIR-contained dependency graph | yes | yes | not applicable (read-only inspection) | not directly evaluated |
| Registered sprung-mass scalar overrides | yes | yes | yes, CarSim 2024.0 | covered by prior rounds |
| Generic scalar override | yes | yes | context-dependent, not generally claimed | pending P2.1 round |
| `SPEED_TARGET_TABLE` via `TableOverride` | yes | yes | yes, CarSim 2024.0 | indirectly covered by routing round |
| Generic `TableOverride` | yes | yes | no; context required | not claimed |
| `ReferenceOverride` dataset-name resolution | yes | yes | no keyword/family compatibility claim | not claimed |
| Isolated batch sweep | yes | yes | core runner already licensed-tested | pass after router fix, P2.1 D |
| Runtime-feedback routing (Simulink / VS API) | yes | yes/docs | Simulink + CarSim passed in final suite | pass, P2.1 E |
| Version-aware generic route | yes | yes | only 2024.0 field-tested | pass, P2.1 H |

Override code uses three machine-readable levels:

- `CARSIM_TESTED`: the exact keyword/path has licensed solver evidence.
- `UNIT_TESTED`: implementation behavior is tested without a licensed solver.
- `CONTEXT_REQUIRED`: syntax exists, but meaning, units, dataset compatibility,
  or version/base behavior still requires local evidence.

The checked-in registry intentionally stays small. Discovery results never
mutate either verified registry.
