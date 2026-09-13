# Contributing

Thanks for improving this skill. The project's core value is that **every mechanism is field-tested** — contributions should preserve that.

## Before you open a PR

1. **Verify against real CarSim.** Describe the scenario, the vehicle base, and the result numbers in your PR. If you document a new keyword or mechanism, record the **exact form that worked**, and note any forms that parse but stay inert (those become pitfalls — see `SKILL.md` §7 for the existing collection).
2. **Run the local checks** (no CarSim needed):
   ```bash
   pip install -r requirements.txt pytest ruff
   ruff check --select E9,F .
   python -m pytest tests/ -q
   ```
3. **Sanitize.** No machine-specific information anywhere: no absolute machine paths (use `<PROG>` / `<DATADIR>` placeholders or generic `C:/work/…` examples), no usernames, conda env names, hardware info, or dataset UUIDs. English only.
4. **Keep the structure intact**: SKILL.md section numbers are cross-reference anchors — don't renumber. If you add/remove files, update the "Where to look first" table in SKILL.md and the Repository layout in the README. New trigger/behavior expectations go into `evals/evals.json` (keep ≥3 positive, ≥2 negative, ≥1 behavior).

The PR template enforces the same checklist.

## Reporting a bug

Open an issue with the **bug report** template: environment (CarSim version, OS, Python), what you ran, what happened vs. what you expected, and the smallest `override.par` + `simfile.sim` pair that reproduces it.

## Proposing a new mechanism

Open an issue with the **mechanism verification** template. The bar for acceptance: evidence, ideally `run_echo.par` lines showing the parsed values plus an A/B comparison run (with/without the override) demonstrating the effect — the same standard the existing recipes were held to (e.g. the Y_CG_SU A/B/C/D experiment in `SKILL.md` §5).
