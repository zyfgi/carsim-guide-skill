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

Retry at most once, and only for a temporary file-access failure or a known
short-lived process/file race. Do not retry license failures, base hash
mismatches, unknown parameters or output units, echo mismatches, scenario
validation errors, version warnings that require user judgment, or repeated
abnormal solver termination. Stop, diagnose, and report the evidence instead.

Do not alter speed, road friction, vehicle mass, or control inputs merely to
make a failed run pass unless the user explicitly asks to debug the physical
configuration.
