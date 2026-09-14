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
| 2026-09-14 | master@19aef30 (P0.1) | pos-1-headless-run | pass | Skill scripts used headlessly (override.par + carsim_batch.py), no GUI, 65 s stop verified; `--read` failed closed on base-emitted unregistered channels (AV_D3f/Throttle/SocBttry) so the channel summary was produced with pandas in native units — documented behavior; selective-subset reading is a P1 improvement note |
| 2026-09-14 | master@19aef30 (P0.1) | neg-3-tire-theory | pass | Theory-only answer with proper sources; no CarSim automation triggered (2 workspace lookups, no execution) |
| 2026-09-14 | master@19aef30 (P0.1) | pos-4-simulink-cosim | partial | Chose real co-simulation (never batch replay as closed loop); IMPORT/EXPORT with two-number PORTS syntax, native units on exports and matlab -batch all correct — but use of the skill's verified builder (references/simulink-cosim.md, scripts/cosim_model.m) is not evidenced; the hand-rolled pipeline hit the known S-function port-materialization issue and reached the step budget |
| 2026-09-15 | master@19aef30 (P0.1) | beh-5-tire-output-allowed | pass | No refusal, no flag, no estimator reroute: all 8 wheel Fx/Fy channels delivered in N from a double-lane-change run. Route deviation: baked DLC base + binary .vsb parsing (MCP read) instead of the skill's WRT/CSV reader; skill use not evidenced in the report |
| 2026-09-15 | master@19aef30 (P0.1) | beh-3-estimator-isolation | fail | Core side correct (Fx/Fy/Fz generated normally, nothing refused), but no hardware whitelist was declared and no estimator/evaluator isolation, manifest or post-run validation was used — all channels were output with "separate at training time" left as a manual step. The optional research workflow was never engaged; see findings below |
| 2026-09-15 | master@19aef30 (P0.1) | beh-6-unknown-keyword-search | partial | Did not guess: located the real inline spring keywords (FS_COMP/EXT_COEFFICIENT, 27 N/mm, exactly 4 occurrences) in the expanded base, modified a copy, verified 29.7 N/mm in the solver input archive, and reran a fair baseline; database datasets untouched. Deviation: edited a copy of the baked Run_all.par instead of the override.par pattern; skill use not evidenced |

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
The executable records are complements to, not substitutes for, fresh-agent
behavioral evaluations.

## Behavior eval round — 2026-09-14/15 (first recorded fresh-session run)

Method: six fresh GLM-5.3-Flash agent sessions (one per case), no shared
context, each receiving only its `evals.json` prompt verbatim plus neutral
harness constraints (work inside the workspace, unique output directories,
~25-tool/10-minute budget, factual final report). Judged against `expect` from
the final reports and the artifacts the sessions produced. Skill version
master@19aef30 (P0.1); a licensed CarSim 2024.0 and a configured CarSim MCP
server were both visible to the sessions.

What the round was checking, and what it showed:

- **Correct triggering** — the headless-run case used the skill's scripts and
  verified termination; the theory negative did not wake the skill.
- **No wrongful workflow loading** — no ordinary task was rerouted into the
  research workflow; tire-force delivery stayed a plain core operation.
- **Fx/Fy no longer refused (P0.1 goal confirmed in practice)** — both
  tire-output cases generated and read wheel forces freely; nobody asked for
  an `allow_truth` flag or similar.
- **Replay vs closed loop** — the closed-loop case chose real Simulink
  co-simulation; nobody presented replay as a closed loop.
- **Keyword guessing** — the suspension case located real keywords
  (FS_COMP_COEFFICIENT / FS_EXT_COEFFICIENT) and verified the change through
  the solver input archive before/after running; no invented keywords.

Gaps recorded for follow-up (P1 candidates, not fixed in this revision):

1. `beh-3` failed: for "data for an online tire-force estimator with Fx/Fy/Fz
   kept for evaluation", the session output every channel and deferred
   estimator blinding to a manual "training time" step — no whitelist, no
   isolation tooling, no manifest. The optional research workflow exists for
   exactly this and was not engaged; routing/discoverability needs work.
2. Several sessions preferred CarSim MCP tools over the skill's verified
   scripts (the MCP solver route crashed once; a hand-rolled co-sim hit the
   known S-function port issue the skill's builder avoids). SKILL.md §8
   already routes MCP to exploration only — the guidance needs to be found
   earlier, not just documented.
3. `read_run_csv` validates every column of the file even when `columns=`
   selects a registered subset, so baked bases emitting extra unregistered
   channels (e.g. AV_D3f, Throttle) cannot be read selectively; documented
   fail-closed, but subset-scoped validation is a candidate improvement.

P1 additions (`beh-7-generic-scenario-yaml`, `beh-8-base-ambiguity-newest`)
are defined but not yet executed in fresh sessions; the manual record table
above stays the single source of truth for executed rounds.
