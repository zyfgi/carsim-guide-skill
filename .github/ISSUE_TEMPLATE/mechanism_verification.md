---
name: New mechanism / keyword proposal
about: Propose a CarSim mechanism, keyword, or recipe to document in the skill
labels: enhancement
---

**The mechanism you want documented**

(e.g. a keyword, an import hook, a table type, a co-sim pattern)

**Evidence (required — the skill only ships field-tested content)**

- [ ] Exact working form (keyword line / syntax as written into override.par)
- [ ] `run_echo.par` lines showing the parsed values
- [ ] A/B comparison: one run without, one run with, demonstrating the effect (numbers)
- [ ] Any forms that parse but stay **inert** (these become pitfalls)

**Where it should live**

- [ ] SKILL.md quick reference (§3 / §5) — small, high-frequency
- [ ] `references/advanced-controls.md` — control-related
- [ ] `references/simulink-cosim.md` — co-simulation
- [ ] a new reference file
