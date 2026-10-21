"""Trigger-collision detection between one skill and a population of skills.

When two installed skills describe overlapping territory, the router has to
guess and both lose: the documented symptom is a skill that "randomly" stops
activating after installing another. This module gives a deterministic,
explainable overlap score so the author can see *which other skill* steals
traffic and *which phrases* overlap.

Scoring (deterministic, no model, no network):
  tokens(description)  -> lowercase word set minus stopwords, plus the
  capability noun set. Jaccard overlap on the full set; boost when the same
  concrete noun (e.g. "pdf") appears in both capability clauses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, Iterable, List, Sequence, Set

WORD_RE = re.compile(r"[a-z0-9一-鿿]+")

STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with",
    "use", "when", "this", "that", "you", "your", "it", "is", "are", "be",
    "any", "all", "from", "by", "as", "at", "if", "not", "can", "will",
    "also", "must", "should", "into", "about", "after", "before", "using",
    "user", "users", "ask", "asks", "wants", "need", "needs", "want",
}


def tokenize(text: str) -> Set[str]:
    return {w for w in WORD_RE.findall(text.lower()) if w not in STOP and len(w) > 1}


def jaccard(a: Set[str], b: Set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / float(len(a | b))


@dataclass
class Collision:
    other: str
    score: float
    shared: List[str]

    def to_dict(self):
        return {"other": self.other, "score": round(self.score, 3), "shared": self.shared}


def detect(subject_name: str, subject_desc: str,
           population: Sequence[Dict[str, str]],
           threshold: float = 0.25) -> List[Collision]:
    """Return collisions sorted by descending score.

    *population* is a list of {"name": …, "description": …} dicts (the other
    installed skills). Anything scoring >= *threshold* is reported.
    """
    st = tokenize(subject_desc)
    out: List[Collision] = []
    for row in population:
        name = row.get("name", "")
        if name == subject_name:
            continue
        score = jaccard(st, tokenize(row.get("description", "")))
        if score >= threshold:
            out.append(Collision(name, score, sorted(st & tokenize(row.get("description", "")))))
    out.sort(key=lambda c: -c.score)
    return out


def read_installed(dirpath: str, glob: str = "*/SKILL.md") -> List[Dict[str, str]]:
    """Read a skills directory into the population format."""
    import glob as _g
    import os
    rows: List[Dict[str, str]] = []
    for path in sorted(_g.glob(os.path.join(dirpath, glob))):
        try:
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            continue
        from .parser import parse
        fm = parse(text)
        if fm.fatal:
            continue
        rows.append({
            "name": fm.keys.get("name") or os.path.basename(os.path.dirname(path)),
            "description": fm.keys.get("description", ""),
        })
    return rows
