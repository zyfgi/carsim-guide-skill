# Parameters: changing vehicle / run values safely

Four tiers, from safest to most powerful. All of them write scenario
override files only — the database stays read-only.

## 1. Typed convenience API (verified)

`VehicleOverrides` covers the five field-verified sprung-mass parameters; SI
in, CarSim mm out:

```python
VehicleOverrides(sprung_mass_kg=1250.0, cg_y_m=0.15, izz_kgm2=1743.0)
```

Sprung mass is absolute (not added payload); sprung-body CG is not the
total-vehicle CG; the Y_CG_SU static-split quirk is documented in SKILL.md §5.

## 2. Generic scalar overrides (keyword confirmed, value native)

`ScalarOverride` carries one keyword, its value **in the CarSim native
unit**, and an echo policy (`required`, `best_effort`, or `none`). Registered
field-tested scalars default to `required`; unknown generic scalars default to
`best_effort`. Only keywords verified on a real base belong in
`parameters.PARAMETER_REGISTRY` (currently the same five above); anything else
must be confirmed first:

```text
natural language ("提高前悬架弹簧刚度 10%")
      -> database_tools.search_database_text / find_datasets / find_keyword
      -> candidate keyword + dataset (confirm unit & context in the dataset file)
      -> confirm it actually took effect via run_echo (inspect_echo_keyword)
      -> ScalarOverride("FS_COMP_COEFFICIENT", 29.7)
```

Never guess a keyword. In YAML:

```yaml
parameters:
  - {keyword: FS_COMP_COEFFICIENT, value: 29.7, echo_validation: required}
```

Validation: keywords are `[A-Z][A-Z0-9_]*` tokens, values finite; overrides
may not duplicate a typed `vehicle` field nor touch Core-managed run/simfile
keywords (timing, paths, DLL, product version, and ports) — conflicts raise at compile time. Post-run,
`check_run` verifies every requested keyword against `run_echo.par`
(known-echo keywords only; unsupported ones are reported, never faked).

## 3. Structured table and dataset reference overrides

`TableOverride` accepts a non-empty, finite rectangular numeric table. Set
`independent_variable="time"` to require a strictly increasing first column.
`ReferenceOverride` accepts an exact `#FullDataName`, resolves it uniquely
inside DATADIR, and rejects arbitrary file paths. These are deliberately
small structures, not a complete `.par` parser.

Each override exposes an `OverrideCapability` from `override_registry.py`.
`SPEED_TARGET_TABLE` is the only table keyword currently marked
`CARSIM_TESTED`. A generic table is `CONTEXT_REQUIRED`. Reference resolution
proves that a named dataset exists; it does **not** prove the reference keyword
accepts that dataset family, so generic references remain `CONTEXT_REQUIRED`.
The scenario manifest records these verification states.

YAML uses `type: table` or `type: reference`; see the scenario schema.

## 4. Escape hatch (advanced CarSim syntax)

Complex `IMPORT`/`EXPORT`, `INSTALL_*` blocks and syntax the API does not
model go through `RawOverride([...])` or legacy `unsafe_extra_lines=[...]` (see
references/advanced-controls.md for the verified torque/brake/steer syntax).
One line per entry; conflicts with typed configuration are rejected. Raw
syntax has no automatic semantic or complex echo guarantee. `extra_lines` is
a deprecated alias.
