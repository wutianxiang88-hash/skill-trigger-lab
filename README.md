# skill-trigger-lab

**Lint, score and live-test whether an agent `SKILL.md` actually gets triggered.**

Every skill author hits the same wall: the skill installs fine, but the agent
never loads it — or loads it on the wrong prompt. The official
[anthropics/skills eval harness hit a 0% trigger rate](https://github.com/anthropics/skills/issues/556),
and [claude-code #9716](https://github.com/anthropics/claude-code/issues/9716) is
one long thread of "my skill won't activate". Most causes are deterministic and
visible in the frontmatter *before* you ever call a model. This tool finds them
offline, in milliseconds, with no API key — then, if you want, measures the real
thing against your host.

```
$ pip install skill-trigger-lab   # or: uv tool run / npx-style one-off, see below
$ skill-trigger-lab lint my-skill/SKILL.md
```

```
## Routability score: 43 / 100 (grade D)

| sev | rule | field | problem |
|---|---|---|---|
| ✗ blocker | `colon-unquoted` | description | unquoted ': ' silently truncates the YAML value — the #1 documented cause of 0% triggers |
| ✗ high | `name-dir-mismatch` | name | name != directory; hosts register the directory and explicit invocation breaks |
| ! medium | `no-trigger-scenario` | description | says what the skill IS, never WHEN to use it |
```

## What it does

| Command | Job | Deterministic? |
|---|---|---|
| `lint` | 14 frontmatter rules: fence position, BOM, unquoted `": "` truncation, name/dir mismatch, length caps, missing "Use when" scenario, unknown keys, empty body | ✅ no model, no network |
| `collision` | overlap score against every installed `SKILL.md` in a directory — shows which sibling skill steals your traffic and the shared tokens | ✅ |
| `gen` | seed eval plan: should-trigger / should-not-trigger probe queries derived from the description | ✅ |
| `score` | one 0–100 routability grade (explicitly a heuristic on description quality, **not** a live routing measurement) | ✅ |
| `run` | live trigger accuracy: pipes each query through **your own** host command, greps the output for skill-activation evidence | host-dependent |

## Install

```bash
# one-off from GitHub (no install)
PYTHONPATH=src python3 -m skill_trigger_lab lint path/to/SKILL.md

# proper
pipx install skill-trigger-lab   # or: uv tool install / pip install .
```

Python ≥ 3.9, zero dependencies.

## The five failures this exists for

1. **Unquoted `": "` in `description`** — `description: e.g. it handles: extraction`
   parses as a nested mapping in several YAML consumers; the router sees an empty
   string. Forever un-triggerable, with no error anywhere. (`colon-unquoted`, blocker)
2. **`name` ≠ directory name** — the spec requires them equal; hosts that key on the
   directory make `/name` invocation dead. (`name-dir-mismatch`, high)
3. **No "Use when …" clause** — selection is driven by scenario language; a pure
   feature list leaves routing to keyword luck. (`no-trigger-scenario`, medium)
4. **Frontmatter invisible** — a BOM or a title line before the opening `---` makes
   the whole block plain prose to strict parsers. (`fm-parse`, blocker)
5. **Trigger collision** — two installed skills with overlapping descriptions split
   (and sometimes lose) the same prompts. `collision` quantifies it.

## `run`: the honest live test

This tool does **not** pretend to observe routing inside a closed host. `run`
takes a bring-your-own runner template that reads the query on stdin, and a
marker regex for what "it fired" looks like on your host:

```bash
skill-trigger-lab gen my-skill/SKILL.md -o evals.json
# humanise the queries in evals.json, then:
skill-trigger-lab run evals.json \
  --cmd 'claude -p "$(cat)" --output-format stream-json 2>&1' \
  --marker '"name":"Skill".{0,40}"skill":"my-skill"'
```

The stream-json marker above matches the same activation evidence the official
anthropics/skills eval runner parses: a `tool_use` block naming the `Skill`
tool with the skill in its input. Per query it prints PASS/FAIL against the
expected polarity and a total accuracy. Exit code `0` only at 100%. Note that
`gen` output is a superset of the official `--eval-set` format (every row
carries `query` + `should_trigger`), so a humanised plan can feed either
runner. If your host gives no observable
activation signal, use `lint` + `collision` + `gen` — they carry no such
dependency, and `score` will tell you, in its `note` field, exactly that it is
not a live measurement.

## CI gate

```yaml
- run: skill-trigger-lab lint my-skill/SKILL.md --json -q
# exit 1 on any blocker/high → fails the build
```

## Limits

- The query generator is template-based; the plans are seeds to humanise, not
  finished benchmarks.
- Collision overlap is bag-of-words Jaccard: good at catching copy-paste twins,
  not paraphrases.
- `run` accuracy is only as good as your runner's activation evidence. State
  your `--cmd` and `--marker` when you quote a number.

## More from this author

- [cn-fin-tie-out](https://github.com/wutianxiang88-hash/cn-fin-tie-out) — an
  Agent Skill for deterministic recomputation of Chinese financial statements:
  the model extracts, the tool checks the arithmetic, a human reads the FAIL
  rows. Built with the same rule this repo enforces — a `SKILL.md` has to say
  when it applies, not just what it is.

## License · MIT. · Author · wutianxiang88-hash
