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

## Record

| Date | Skill version | Case | Verdict | Notes |
|---|---|---|---|---|
| | | | | (no runs recorded yet — add one row per case per skill version) |

## Scope boundaries

The negative cases pin down the skill's edges: generic CSV/pandas work and
document editing are not CarSim contexts and must not wake the skill. If you
add cases, add at least one negative for every new trigger phrase you add to
the SKILL.md `description` — trigger phrases without a matching negative are
how skills become over-eager.
