# Parameter discovery

Use `discover_parameter(query, datadir, root_dataset=None, run_echo=None)`.
It returns a `ParameterDiscoveryReport`; only exact registry or documented
alias evidence populates `report.resolved`.

The fixed search order is:

1. exact `PARAMETER_REGISTRY` match;
2. exact verified alias;
3. line-initial keyword search;
4. dataset-name and free-text search;
5. optional referenced-dataset restriction via the dependency graph;
6. optional echo context inspection;
7. unresolved.

Database and echo hits are candidates (`strong` or `weak`), not automatic
verification. Use `format_discovery_report(report)` to expose keyword,
dataset, context, unit hint, confidence, and reason. If multiple candidates
remain, ask for/obtain better context instead of selecting the first.

Before creating an override, verify physical meaning, native unit, dataset
context, and—after a run—the actual echo value.
