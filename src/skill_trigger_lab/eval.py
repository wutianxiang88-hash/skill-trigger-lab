"""Seed-eval generation and routability scoring.

Two deterministic jobs:

*gen*  — build an eval plan (should-trigger / should-not-trigger queries)
         from a SKILL.md *without calling any model*. Templates are derived
         from the description's "Use when …" clauses, its capability nouns,
         and explicit exclusion sentences. The plan is a starting corpus:
         authors (or a model) are expected to humanise the phrasing. The
         file format is a superset of the common `evals.json` shape so the
         generated corpus is directly consumable by external runners.

*score* — compress the lint + collision signals into one 0–100 routability
          score with a ranked list of concrete rewrite suggestions. The
          score is heuristic by design and the report labels it as such;
          it measures description quality, not live routing.
"""

from __future__ import annotations

import json
import re
from typing import Dict, List

from .lint import BLOCKER, HIGH, MEDIUM, LOW, Finding

_CAP_RE = re.compile(
    r"use when|also use|apply when|适用于|使用当|当用户|触发语|trigger", re.I)
_EXCL_RE = re.compile(
    r"(?:do not|don't|not for|never|不用于|不适用于|excluding|except)\s+([^.;。；]+)", re.I)
_QUOTED_RE = re.compile(r"[「“\"']([^」”\"']{4,60})[」”\"']")


def gen_queries(name: str, description: str, body: str = "") -> List[Dict[str, object]]:
    """Generate a deterministic seed eval plan."""
    queries: List[Dict[str, object]] = []
    qid = 0
    seen = set()

    def add(kind: str, text: str, note: str = "") -> None:
        nonlocal qid
        text = " ".join(text.split())[:160]
        if not text or (kind, text) in seen:
            return
        seen.add((kind, text))
        qid += 1
        queries.append({"id": "q%02d" % qid, "kind": kind, "query": text, "note": note})

    # ---- positives: from "Use when" clauses ----
    clauses = [c.strip() for c in re.split(r"[;;。]|\.\s", description) if c.strip()]
    pos_clauses = [c for c in clauses
                   if (_CAP_RE.search(c) or re.search(r"\b(when|for|if|包括|包含)\b", c, re.I))
                   and not _EXCL_RE.search(c)]
    if not pos_clauses:
        pos_clauses = [c for c in clauses if not _EXCL_RE.search(c)][:2]

    cap_noun = _capability_noun(description)
    for c in pos_clauses[:4]:
        task = _to_task_phrase(c)
        if not task:
            continue
        add("should_trigger", "I need help: " + task, "derived from: %s" % c[:80])
        add("should_trigger", "Is there a way to %s ?" % task[:120], "question phrasing")
    if cap_noun:
        add("should_trigger", "please run the %s on this file" % name, "imperative probe (name mention)")
        add("should_trigger", "帮我做一次%s" % cap_noun, "chinese imperative probe")

    # quoted trigger phrases in body ("触发语：「…」")
    for m in _QUOTED_RE.finditer(body or ""):
        if len(queries) < 14:
            add("should_trigger", m.group(1), "quoted phrase from body")

    # ---- negatives ----
    # 1) exclusion sentences honoured
    for c in clauses:
        m = _EXCL_RE.search(c)
        if m:
            add("should_not_trigger", "帮我处理一下：%s" % m.group(1).strip()[:60],
                "explicit exclusion honoured")
    # 2) concept-only probes (routing must not fire on keywords alone)
    if cap_noun:
        add("should_not_trigger",
            "what is %s ? just explain the concept, do nothing" % cap_noun,
            "definition-only probe")
    for c in pos_clauses[:2]:
        task = _to_task_phrase(c)
        if task:
            add("should_not_trigger",
                "what kind of tool would one use to %s ? I am not asking you to do it" % task[:80],
                "meta-question probe")
    # 3) unrelated baseline
    add("should_not_trigger", "write me a haiku about the sea", "unrelated control")

    return queries


def _capability_noun(description: str) -> str:
    """First capability noun phrase, ignoring exclusion sentences."""
    scrubbed = " ".join(c for c in re.split(r"[;;。]|\.\s", description)
                        if not _EXCL_RE.search(c))
    m = re.search(r"\bfor ([a-z][a-z ]{2,40}?)(?:[,.;]|$)", scrubbed, re.I)
    if m:
        return m.group(1).strip().lower()
    m = re.search(r"\b([a-z][a-z ]{2,30}?(?:checks|analysis|extraction|audit|lint|report|forms))\b",
                  scrubbed, re.I)
    if m:
        return m.group(1).strip().lower()
    return ""


def _to_task_phrase(clause: str) -> str:
    """'Use when the user asks to fill a PDF form' -> 'fill a PDF form'.

    Strips scenario markers and attribution preambles; returns '' when the
    remainder has no verb-ish content (guards against nonsense probes).
    """
    t = re.sub(r"^\W*use when\W*", "", clause, flags=re.I)
    t = re.sub(r"^(?:the\s+)?(?:agent|user|you|model)s?\s+(?:asks?\s+to|wants?\s+to|"
               r"needs?\s+to|requests?\s+to|tries\s+to)\s+", "", t, flags=re.I)
    t = re.sub(r"^(?:当用户|适用于|使用当)\s*", "", t)
    t = t.strip().strip(".,;: ")
    if len(t) < 8 or not re.search(r"[a-zA-Z一-鿿]", t):
        return ""
    return t


# ---------------------------------------------------------------------------
# scoring
# ---------------------------------------------------------------------------

_PENALTY = {BLOCKER: 35, HIGH: 15, MEDIUM: 7, LOW: 3}


def score(lint_findings: List[Finding], collisions) -> Dict[str, object]:
    pts = 100
    for f in lint_findings:
        pts -= _PENALTY.get(f.severity, 3)
    if collisions:
        top = max(c.score for c in collisions)
        pts -= int(min(20, max(0.0, (top - 0.5)) * 40))
    pts = max(0, pts)
    grade = ("A" if pts >= 90 else "B" if pts >= 75 else
             "C" if pts >= 60 else "D" if pts >= 40 else "F")
    suggestions = [f.fix for f in lint_findings if f.fix]
    ranked = sorted(lint_findings,
                    key=lambda f: {"blocker": 0, "high": 1, "medium": 2, "low": 3}[f.severity])
    return {
        "points": pts,
        "grade": grade,
        "note": "heuristic description-quality score, not a live routing measurement",
        "ranked_findings": [f.rule for f in ranked],
        "suggestions": suggestions[:6],
    }


def dump_plan(path: str, name: str, queries: List[Dict[str, object]],
              meta: Dict[str, object] = None) -> None:
    """Write an eval plan.

    Each row carries a `should_trigger` boolean in addition to `kind`, so the
    `evals` array is directly consumable by the official
    anthropics/skills run_eval.py `--eval-set` format ([{query, should_trigger}]).
    """
    evals = []
    for q in queries:
        row = dict(q)
        row["should_trigger"] = q["kind"] == "should_trigger"
        evals.append(row)
    payload = {
        "skill": name,
        "generated_by": "skill-trigger-lab",
        "meta": meta or {},
        "evals": evals,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def load_plan(path: str) -> Dict[str, object]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
