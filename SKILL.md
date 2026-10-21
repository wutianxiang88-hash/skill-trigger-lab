---
name: skill-trigger-lab
description: Lint, score and live-test whether an agent skill file actually gets triggered. Use when an author writes or debugs a SKILL.md and the skill installs but never activates, activates on the wrong prompt, or collides with another installed skill; when a frontmatter YAML trap needs to be found offline; or when a CI gate should fail on un-triggerable skills. Runs deterministically with no model call and no API key.
license: MIT
compatibility: Python 3.9 or newer. No third-party packages. The live `run` command additionally needs a host CLI configured by the user.
---

# skill-trigger-lab

Find, offline and deterministically, why a `SKILL.md` never triggers — then
optionally measure the real trigger rate against your own host.

## When to use this skill

Use it whenever a skill misbehaves at the routing layer:

- a skill is installed but the agent never loads it;
- it loads on prompts it should not;
- two installed skills steal each other's traffic;
- you want CI to reject un-triggerable frontmatter before merge.

Do not use it to judge whether a skill's *instructions* are good, or to
measure model quality. It audits the trigger surface only.

## Hard rule

Fix every `blocker` and `high` finding before any live test. A live trigger
run against a file with an unquoted `": "` in its description measures
garbage.

## Workflow

1. `skill-trigger-lab lint path/to/SKILL.md` — read the findings; apply the
   suggested fixes. The report's score is a heuristic on description quality,
   labelled as such; never quote it as a routing measurement.
2. `skill-trigger-lab collision path/to/SKILL.md --installed ~/.claude/skills` —
   if a sibling scores above 0.5 overlap, sharpen the descriptions apart.
3. `skill-trigger-lab gen ... -o evals.json` — then humanise the seed queries.
   Quote template-derived accuracy anywhere as meaningless without this step.
4. `skill-trigger-lab run evals.json --cmd '<your host CLI>' --marker '<regex>'`
   — report `--cmd`, `--marker` and query count together with any accuracy
   number. Exit codes — 0 clean, 1 gate findings, 2 unreadable input.
