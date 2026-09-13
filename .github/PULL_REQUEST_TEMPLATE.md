## What & why

<!-- One paragraph: what does this change do, and why? Link any related issue. -->

## Verification

This project's core value is that everything is **field-tested**. Please tell us how you verified your change:

- [ ] Ran against real CarSim (describe: scenario, vehicle base, result numbers if applicable)
- [ ] Syntax/JSON validated (`python -m ast` / `json.load` — CI also checks this)
- [ ] If a new mechanism or keyword is documented: the exact form that worked is recorded (and any inert/misleading forms are noted as pitfalls)

## Skill structure

- [ ] `SKILL.md` "Where to look first" table updated if files were added/removed (section numbers and cross-reference anchors unchanged)
- [ ] New pitfalls added to `SKILL.md` §7 if a trap was discovered
- [ ] `evals/evals.json` updated if triggers/behavior changed (keep ≥3 positive, ≥2 negative, ≥1 behavior)
- [ ] README (What it does / Repository layout) updated if the surface changed

## Sanitization

The skill must contain **no machine-specific information**:

- [ ] No absolute machine paths (`D:\…`, `C:\Users\<name>\…` — use `<PROG>` / `<DATADIR>` placeholders or generic `C:/work/…` examples)
- [ ] No usernames, conda env names, hardware info, or dataset UUIDs (locate datasets by name, never hardcode)
- [ ] English only (no CJK characters anywhere)

## Checklist

- [ ] CI passes (frontmatter, syntax, evals structure, size limits)
- [ ] Docs are concise: state what to do rather than narrating (official skill-authoring guidance)
