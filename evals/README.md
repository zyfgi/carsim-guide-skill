# Evals: trigger & behavior protocol

`evals.json` is a **manual harness by design**. Each case asks whether an
agent *should* activate this skill and whether it then follows the documented
discipline — judgments about agent behavior that need a fresh LLM session and
a human (or LLM) judge, not something a shell script can decide. What CI does
automate is the *structure*: `ci.yml` validates that the file parses and keeps
the shape (≥3 positive triggers, ≥2 negative triggers, ≥1 behavior case, unique
ids) so the suite cannot silently rot.

## Running the suite

For each case in `evals/evals.json`:

1. Start a **fresh agent session** (no conversation history) with this skill
   installed.
2. Paste the `prompt` verbatim.
3. Judge the observed behavior against `expect`:
   - `positive_trigger` — the skill should activate and the agent should
     follow the referenced mechanism.
   - `negative_trigger` — the skill should NOT activate; the agent should
     treat it as ordinary work in its own domain.
   - `behavior` — the skill activates AND the agent follows the stated
     discipline (e.g. refusing the documented-broken route).
4. Record the verdict (and the session transcript link / notes) in the table
   below. One row per case per skill version.

## Executable verification records

Run `python evals/run_checks.py --output evals/results/<version>.json` to execute
the Python contract tests and save per-case outcomes, source hashes and versions.
Add `--functional` for the licensed solver tests (an explicitly selected base is
required), and repeat `--live-manifest <path>` to include completed research runs.
The recorder checks the manifest's artifact hashes before accepting live evidence.
Use `--rejected-manifest` to record a real solver rejection separately from accepted experiments.
Records are immutable by convention: the script refuses an existing output path.

These records do not claim that a fresh agent activated the skill correctly.
Manual trigger/behavior cases below require separate fresh-session evidence.

## Manual trigger record

| Date | Skill version | Case | Verdict | Notes |
|---|---|---|---|---|
| | | | | (no runs recorded yet — add one row per case per skill version) |

## Scope boundaries

The negative cases pin down the skill's edges: generic CSV/pandas work and
document editing are not CarSim contexts and must not wake the skill. If you
add cases, add at least one negative for every new trigger phrase you add to
the SKILL.md `description` — trigger phrases without a matching negative are
how skills become over-eager.

## Results from this revision

- `results/2026-09-14-research-contract-v1.json`: 68 Python contract tests and three accepted licensed research experiments.
- `results/2026-09-14-research-contract-v1-final.json`: the initial full regression attempt, including the MATLAB sandbox startup failure. This is retained as failure evidence.
- `results/2026-09-14-research-contract-v1-verified.json`: MATLAB initialized outside the sandbox and exposed a missing DATADIR separator in the old simfile generator. The stalled test was stopped and recorded as failed.
- `results/2026-09-14-research-contract-v1-complete.json`: full regression after fixing directory separators and passing one timing configuration through Python, CarSim and MATLAB; see its per-case verdicts.

The research runs cover 1 ms integration with 100 Hz sensor replay and a 0.5 ms
mass/CG/inertia variant including motor RPM-to-rad/s conversion. A 5 ms variant
was rejected after this particular base became numerically unstable. Matching
TSTEP and EXT_MODEL_STEP does not make an arbitrary step numerically stable.
Embedded solver log tails inside rejection `error` fields are redacted to
`<PROG>`/`<DATADIR>`/`<RUNTIME>` placeholders — machine install paths must not
be published; `run_checks.py` applies this redaction automatically.
Manual skill-trigger judgments remain unrun; these executable records are not
substitutes for fresh-agent behavioral evaluations.
