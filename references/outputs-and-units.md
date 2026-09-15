# Output discovery and units

Use `scripts/output_registry.py` as the authority for verified channel names,
native units, SI conversions, categories, descriptions, and aliases.

## Unknown output workflow

1. Call `resolve_output_alias(text)`. It performs exact verified alias lookup;
   an empty result means “unknown,” not permission to infer a channel.
2. Call `find_output_candidates(text, sources=[...])` over relevant prior
   `run.csv`, `run_echo.par`, or CarSim output-definition files.
3. Show each candidate with its source line. A candidate without an
   `OutputSpec` is weak and must not be requested yet.
4. Confirm the channel spelling and native unit in an authoritative local
   definition or successful run, then add a reviewed registry entry and test.
5. Request the verified channel and confirm it is present in the fresh CSV.

`find_output_candidates` never fabricates a name. Do not bulk-add plausible
CarSim names for coverage.

## CSV reading contract

```python
read_run_csv("run.csv", columns=["Time", "Vx"])
```

With `columns=[...]`, only requested columns must have registered units; an
unrequested custom column is ignored. With `columns=None`, every retained
column must be registered. Missing Time/requested columns, unknown units, and
non-numeric selected values fail closed. `units="native"` disables SI scaling.

Verified conversions include Vx/Vy km/h→m/s, Ax/Ay g→m/s², angles deg→rad,
angular speeds rpm→rad/s, and force/torque identity conversions.
