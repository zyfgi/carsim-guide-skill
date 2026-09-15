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

For a uniform road-friction sweep, use the already verified scenario field
`road.friction` exactly as shown above. Core compiles that field to its owned
`MU_ROAD_CARPET` table. Do **not** reroute this ordinary field through parameter
discovery, invent `parameters.<friction_keyword>`, or treat it as a generic
scalar. Parameter discovery is only for physical quantities that do not
already have a typed scenario field.

Run with:

```text
python scripts/batch_runner.py examples/batches/friction_sweep.yaml --registry bases.local.json --out runs --run
```

Output is `runs/<batch-id>/run_0001/...` with an immutable scenario snapshot,
normal per-run artifacts/manifest, plus `batch_manifest.json`. Failures are
recorded and isolated by default; `--fail-fast` stops after the first failure.
The batch manifest records SHA256 values for both the batch configuration and
its base scenario, along with every expanded parameter combination and run
manifest path.
Batch members execute sequentially. Concurrent multi-solver execution is not
enabled because license and multi-instance solver behavior are not verified.
