# Structured troubleshooting

Run `python scripts/diagnose_run.py <run-directory>`. The command reports
PASS/FAIL/NOT RUN by layer and returns nonzero when an error is found.

Stable layers are: environment, base, scenario, compile, solver, license,
output, echo, database, cosim, and version. Stable exception classes live in
`scripts/carsim_errors.py`.

The first diagnostic pass recognizes only evidence-backed signatures:

- missing CLI executable or DLL;
- simfile not pinning `carsim_64.dll`;
- license / “Unable to load library” text;
- missing normal termination;
- missing, stale, or unparsable `run.csv`;
- missing echo or scalar echo mismatch;
- unverified CarSim version.

Do not classify unfamiliar solver prose speculatively. Preserve the original
exception/stdout and ask for the relevant artifact when evidence is missing.
