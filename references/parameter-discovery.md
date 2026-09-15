# Parameter discovery

Use `discover_parameter(query, datadir, root_dataset=None, run_echo=None,
search_terms=None)`.
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

`normalize_parameter_query` uses the same `DiscoveryQuery` contract as output
discovery. Chinese physical descriptions may expand to English physical search
terms. Search terms are evidence queries only: they never become a generated
CarSim keyword. Only a literal line-initial token found in a database or echo
can become a candidate. Explicitly empty search terms fail closed as
unresolved, and discovery never adds candidates to `PARAMETER_REGISTRY`.

Database and echo hits are candidates (`strong` or `weak`), not automatic
verification. Use `format_discovery_report(report)` to expose keyword,
dataset, context, unit hint, confidence, and reason. If multiple candidates
remain, ask for/obtain better context instead of selecting the first.

Before creating an override, verify physical meaning, native unit, dataset
context, and—after a run—the actual echo value.
