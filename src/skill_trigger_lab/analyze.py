"""Analyze one SKILL.md: lint + collision + score + seed plan, in one call."""

from __future__ import annotations

import os
from typing import Dict, List, Optional

from . import collision as _coll
from . import eval as _ev
from .lint import Finding, lint
from .parser import directory_name, parse
from .report import SkillReport


def analyze_file(path: str,
                 population: Optional[List[Dict[str, str]]] = None,
                 threshold: float = 0.25) -> SkillReport:
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except OSError as exc:
        rep = SkillReport(file=path)
        rep.error = "cannot read file: %s" % exc
        return rep

    text = raw.decode("utf-8-sig", errors="strict") if _is_utf8(raw) else \
        raw.decode("utf-8", errors="replace")
    fm = parse(text)
    dir_hint = directory_name(path)
    findings: List[Finding] = lint(fm, "" if not fm.present else dir_hint)
    name = fm.keys.get("name") or dir_hint or os.path.basename(path)

    desc = fm.keys.get("description", "")
    collisions = []
    if population and desc:
        collisions = _coll.detect(name, desc, population, threshold=threshold)

    sc = _ev.score(findings, collisions)

    queries = []
    if desc:
        queries = _ev.gen_queries(name, desc, fm.body)

    rep = SkillReport(skill=name, file=path, findings=findings,
                      collisions=collisions, score=sc,
                      plan_queries=len(queries))
    if fm.fatal:
        rep.error = fm.fatal
    return rep


def _is_utf8(b: bytes) -> bool:
    try:
        b.decode("utf-8")
        return True
    except UnicodeDecodeError:
        return False
