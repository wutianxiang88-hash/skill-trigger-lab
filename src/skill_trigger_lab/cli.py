"""skill-trigger-lab CLI.

Subcommands:

  lint      deterministic frontmatter lint (exit 1 on blocker/high)
  gen       generate a seed eval plan (evals.json) — no model, no network
  collision overlap check against an installed-skills directory
  score     one-line routability score
  run       live trigger test via a BRING-YOUR-OWN runner command

The `run` command is the honest one: this tool does NOT pretend to measure
routing inside a closed host. You give it a shell command template that,
given a query on stdin, prints whatever the host emitted; the runner greps
for skill-load evidence (configurable marker regex) and tallies hits.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
import sys

from . import __version__
from .analyze import analyze_file
from .collision import detect, read_installed
from .eval import dump_plan
from .parser import parse


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skill-trigger-lab",
        description="Lint, score and (optionally) live-test the triggering of an agent SKILL.md.")
    p.add_argument("--version", action="version", version="skill-trigger-lab " + __version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_target(sp):
        sp.add_argument("skill_file", help="path to SKILL.md")

    sp = sub.add_parser("lint", help="static frontmatter lint")
    add_target(sp)
    sp.add_argument("-o", "--output", help="write markdown report")
    sp.add_argument("--json", action="store_true", help="machine-readable output")
    sp.add_argument("--installed", metavar="DIR",
                    help="also run collision check against DIR/*/SKILL.md")
    sp.add_argument("--threshold", type=float, default=0.25)
    sp.add_argument("-q", "--quiet", action="store_true")

    sp = sub.add_parser("gen", help="generate a seed eval plan (evals.json)")
    add_target(sp)
    sp.add_argument("-o", "--output", default="evals.json")
    sp.add_argument("-n", "--max", type=int, default=24)

    sp = sub.add_parser("collision", help="trigger-collision check")
    add_target(sp)
    sp.add_argument("--installed", required=True, metavar="DIR")
    sp.add_argument("--threshold", type=float, default=0.25)
    sp.add_argument("--json", action="store_true")

    sp = sub.add_parser("score", help="one-line routability score")
    add_target(sp)

    sp = sub.add_parser("run", help="live trigger test with a bring-your-own runner")
    sp.add_argument("plan", help="evals.json produced by `gen`")
    sp.add_argument("--cmd", dest="runner", required=True,
                    help="shell template; the query is passed on stdin. "
                         "Example: 'claude -p \"$(cat)\" --output-format text'")
    sp.add_argument("--marker", default=None,
                    help="regex (case-insensitive) whose presence in the host output "
                         "counts as skill activation. Default: the skill name itself.")
    sp.add_argument("--json", action="store_true")
    sp.add_argument("-o", "--output", help="write results json")
    return p


# ---------------------------------------------------------------------------

def _print_md(rep, out_path=None, quiet=False):
    md = rep.to_markdown()
    if out_path:
        with open(out_path, "w", encoding="utf-8") as fh:
            fh.write(md)
    if not quiet or out_path is None:
        print(md)


def cmd_lint(args):
    pop = read_installed(args.installed) if args.installed else None
    rep = analyze_file(args.skill_file, population=pop, threshold=args.threshold)
    if args.json:
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
    else:
        _print_md(rep, args.output, args.quiet)
        if not args.quiet:
            print(rep.summary_line(), file=sys.stderr)
    return rep.exit_code()


def cmd_gen(args):
    with open(args.skill_file, encoding="utf-8-sig") as fh:
        fm = parse(fh.read())
    name = fm.keys.get("name") or os.path.basename(os.path.dirname(args.skill_file))
    desc = fm.keys.get("description", "")
    if not desc:
        print("no description to derive queries from — fix the lint errors first "
              "(run `skill-trigger-lab lint`).", file=sys.stderr)
        return 1
    queries = __import__("skill_trigger_lab.eval", fromlist=["gen_queries"]).gen_queries(
        name, desc, fm.body)[: args.max]
    dump_plan(args.output, name, queries,
              meta={"source": args.skill_file, "kind": "seed",
                    "note": "template-derived; humanise phrasing before trusting scores"})
    pos = sum(1 for q in queries if q["kind"] == "should_trigger")
    print("wrote %s: %d queries (%d should_trigger / %d should_not_trigger)" % (
        args.output, len(queries), pos, len(queries) - pos))
    return 0


def cmd_collision(args):
    with open(args.skill_file, encoding="utf-8-sig") as fh:
        fm = parse(fh.read())
    name = fm.keys.get("name") or ""
    desc = fm.keys.get("description", "")
    pop = read_installed(args.installed)
    cols = detect(name, desc, pop, threshold=args.threshold)
    if args.json:
        print(json.dumps([c.to_dict() for c in cols], ensure_ascii=False, indent=2))
    else:
        if not cols:
            print("no collisions above %.2f among %d installed skills" % (
                args.threshold, len(pop)))
        for c in cols:
            print("%s  %.2f  %s" % (c.other, c.score, ", ".join(c.shared[:8])))
    return 1 if cols else 0


def cmd_score(args):
    rep = analyze_file(args.skill_file)
    print("%s: %d/100 (%s)" % (rep.skill, rep.score["points"], rep.score["grade"]))
    return rep.exit_code()


def cmd_run(args):
    plan = json.load(open(args.plan, encoding="utf-8"))
    skill = plan.get("skill", "")
    marker = re.compile(args.marker or r"\b%s\b" % re.escape(skill), re.I)
    cmd_tmpl = args.cmd
    results = []
    n_pass = 0
    for q in plan.get("evals", []):
        text = q["query"]
        expect = q["kind"] == "should_trigger"
        try:
            proc = subprocess.run(
                cmd_tmpl, shell=True, input=text.encode("utf-8"),
                capture_output=True, timeout=180)
            out = proc.stdout.decode("utf-8", "replace") + proc.stderr.decode("utf-8", "replace")
            fired = bool(marker.search(out))
        except subprocess.TimeoutExpired:
            out, fired = "<timeout>", False
        ok = fired == expect
        n_pass += int(ok)
        results.append({"id": q["id"], "kind": q["kind"], "query": text,
                        "expected_trigger": expect, "observed_trigger": fired,
                        "match": ok, "output_len": len(out)})
        print("%s  %-18s expect=%-5s observed=%-5s  %s" % (
            "PASS" if ok else "FAIL", q["kind"], expect, fired, text[:70]))
    total = len(results)
    rate = (n_pass / total * 100) if total else 0.0
    print("\naccuracy: %d/%d = %.1f%%  (skill=%s marker=%s)" % (
        n_pass, total, rate, skill, args.marker or "skill-name"))
    if args.output:
        json.dump({"skill": skill, "accuracy": rate, "results": results},
                  open(args.output, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return 0 if rate >= 100 else 1


def main(argv=None):
    args = build_parser().parse_args(argv)
    return {"lint": cmd_lint, "gen": cmd_gen, "collision": cmd_collision,
            "score": cmd_score, "run": cmd_run}[args.cmd](args)
