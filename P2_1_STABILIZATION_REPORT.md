# CarSim Guide Skill — P2.1 stabilization report

Date: 2026-09-15

## 1. Problems fixed

- Non-ASCII output queries can no longer become match-all searches.
- Output and parameter discovery now preserve evidence and never promote a
  search phrase into an invented CarSim identifier.
- Dataset dependency traversal stops at the DATADIR boundary by default,
  including through the legacy API.
- Structured overrides expose evidence-specific verification states.
- Echo-policy defaults now distinguish registered from generic scalars.
- Agent routing explicitly prefers verified skill paths.

## 2. Files changed

Core additions are `scripts/discovery_query.py` and
`scripts/override_registry.py`. Discovery changes are in
`scripts/output_registry.py` and `scripts/parameter_discovery.py`; containment
is in `scripts/database_tools.py`; override status/manifest changes are in
`scripts/parameters.py` and `scripts/scenario_runner.py`. Tests are in
`tests/test_p2_1_stabilization.py` and `tests/functional_carsim.py`. Router,
reference, capability, eval, and evidence files are updated under `SKILL.md`,
`references/`, and `evals/`.

## 3. Multilingual discovery strategy

A shared `DiscoveryQuery(original, search_terms, aliases)` separates user
wording from literal evidence queries. Chinese descriptions expand only to
English physical search phrases, never to CarSim channels or keywords. Empty
terms return unresolved/empty. Candidates must contain literal artifact or
database evidence, retain ambiguity, and cannot mutate either verified
registry.

## 4. DATADIR containment strategy

`build_dependency_graph(..., allow_external=False)` creates an
`external=True` node and `external_reference` issue for an outside target, then
stops. Explicit opt-in allows recursion while retaining external markers on
descendants. `resolve_dataset_tree` uses the same boundary.

## 5. Override verification model

`override_registry.py` defines `UNIT_TESTED`, `CARSIM_TESTED`, and
`CONTEXT_REQUIRED`. Registered sprung-mass scalars are CarSim-tested. Generic
scalar/table/reference/raw paths require context. Scenario manifests record
the selected capability state and evidence. Registered scalars default to
required echo; unknown scalars default to best-effort echo.

## 6. TableOverride actual verification status

The exact `SPEED_TARGET_TABLE` typed path is **implemented, unit-tested, and
CarSim-tested on 2024.0**. The licensed test passed a `TableOverride` through
the structured compiler path, observed normal solver termination, fresh
non-empty CSV/log artifacts, exactly two requested echo rows, and a vehicle
speed increase. Other table keywords remain `CONTEXT_REQUIRED`.

## 7. ReferenceOverride actual verification status

Exact in-DATADIR dataset-name resolution is implemented and unit-tested.
Keyword-to-dataset-family compatibility is separate and remains
`CONTEXT_REQUIRED`; no generic licensed claim was made because no safe case was
guessed.

## 8. Unit tests

The unit-only run completed with **153 total, 153 passed, 0 failed, 0
skipped**. P2.1 cases cover three Chinese output queries, empty-token behavior,
candidate evidence, registry immutability, Chinese parameter search,
ambiguity, external containment, capability states, and all echo policies.

## 9. Licensed tests

The final combined regression contains **158 total, 158 passed, 0 failed, 0
skipped**: 153 unit tests plus five real functional tests. Licensed coverage
includes torque import, throttle/brake, base speed-table replacement, typed
`TableOverride`, and MATLAB/Simulink + CarSim end-to-end co-simulation.
Evidence: `evals/results/2026-09-15-p2-1-final.json`.

## 10. GPT-5.6 behavior eval

Eight independent `gpt-5.6-luna` fresh sessions evaluated A–H. A–C and E–H
passed first try. D was initially partial, prompted a documentation-only
friction-field routing fix, then passed in a new fresh session. Final score:
**8 PASS, 0 PARTIAL, 0 FAIL**. Evidence:
`evals/results/2026-09-15-p2-1-luna-behavior.json`.

## 11. Capabilities that remain unverified

Only CarSim 2024.0 is field-tested. Generic table schemas, generic scalar
meaning/units, and reference keyword-family compatibility need local evidence.
VS API stepping remains a prototype route unless separately validated. These
limits are intentional and are not silently promoted to supported registry
entries.

## 12. P3 recommendations

P2 is frozen for the requested scope. Enter P3 only from explicit new
requirements, and keep the same promotion rule: implement → unit-test → obtain
licensed evidence where applicable → run independent agent evals → update the
capability table. Do not expand registries speculatively.
