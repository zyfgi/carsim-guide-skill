# Batch sweeps

`scripts/batch_runner.py` expands one validated base scenario and delegates
every member to `scenario_runner.run_scenario`.

```yaml
batch: {id: mass_mu_grid}
base_scenario: ../scenarios/basic_cruise.yaml
combination: cartesian
sweep:
  parameters.M_SU: {values: [1100, 1200, 1300]}
  road.friction: {values: [0.6, 0.8]}
```

`cartesian` produces every combination. `zip` pairs equal-length value lists.
Only existing nested scenario fields and `parameters.<KEYWORD>` are valid
targets. Complex DOE/optimization is intentionally outside this layer.

Run with:

```text
python scripts/batch_runner.py examples/batches/friction_sweep.yaml --registry bases.local.json --out runs --run
```

Output is `runs/<batch-id>/run_0001/...` with an immutable scenario snapshot,
normal per-run artifacts/manifest, plus `batch_manifest.json`. Failures are
recorded and isolated by default; `--fail-fast` stops after the first failure.
