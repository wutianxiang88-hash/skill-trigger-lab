# Changelog

## 0.1.0

Initial release.

- `lint` — 14 deterministic frontmatter rules (fence position, BOM, unquoted
  `": "` silent truncation, name/directory mismatch, length caps, missing
  "Use when" scenario, unknown keys, empty body, generic openers, thin
  descriptions). Markdown + JSON output, CI-friendly exit codes.
- `collision` — bag-of-words overlap scoring of one description against an
  installed-skills directory, with shared-token explanations.
- `gen` — deterministic seed eval plans (should-trigger / should-not-trigger)
  derived from the description's scenario and exclusion clauses.
- `score` — 0–100 routability heuristic, explicitly labelled as non-live.
- `run` — bring-your-own-runner live trigger accuracy with a configurable
  activation marker.
- Pure standard library, Python ≥ 3.9, zero dependencies, no network.
