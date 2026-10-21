"""Report rendering for skill-trigger-lab (Markdown + JSON).

The JSON envelope is the machine-readable contract for CI and agents:

  { "skill", "file", "findings": [...], "collisions": [...],
    "score": {...}, "verdict": "clean|gate|error", "plan_queries": N }

verdict mirrors the exit-code contract:
  clean  (0)  no blocker/high findings
  gate   (1)  at least one blocker/high — CI should fail
  error  (2)  the file itself could not be read or parsed at all
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import List, Optional

from .lint import Finding

SEV_ORDER = {"blocker": 0, "high": 1, "medium": 2, "low": 3}
SEV_ICON = {"blocker": "✗", "high": "✗", "medium": "!", "low": "~"}


@dataclass
class SkillReport:
    skill: str = ""
    file: str = ""
    findings: List[Finding] = field(default_factory=list)
    collisions: list = field(default_factory=list)
    score: Optional[dict] = None
    plan_queries: int = 0
    error: Optional[str] = None

    # ------------------------------------------------------------------
    def verdict(self) -> str:
        if self.error:
            return "error"
        if any(f.severity in ("blocker", "high") for f in self.findings):
            return "gate"
        return "clean"

    def exit_code(self) -> int:
        return {"clean": 0, "gate": 1, "error": 2}[self.verdict()]

    def counts(self) -> dict:
        c = {"blocker": 0, "high": 0, "medium": 0, "low": 0}
        for f in self.findings:
            c[f.severity] = c.get(f.severity, 0) + 1
        return c

    # ------------------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "tool": "skill-trigger-lab",
            "skill": self.skill,
            "file": self.file,
            "verdict": self.verdict(),
            "exit_code": self.exit_code(),
            "error": self.error,
            "findings": [f.to_dict() for f in sorted(
                self.findings, key=lambda x: SEV_ORDER.get(x.severity, 9))],
            "collisions": [c.to_dict() for c in self.collisions],
            "score": self.score,
            "plan_queries": self.plan_queries,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    def summary_line(self) -> str:
        c = self.counts()
        bits = ["%s=%d" % (k.upper(), v) for k, v in c.items() if v]
        if self.score:
            bits.append("score=%d(%s)" % (self.score["points"], self.score["grade"]))
        if self.collisions:
            bits.append("collisions=%d" % len(self.collisions))
        bits.append("verdict=%s" % self.verdict())
        bits.append("exit=%d" % self.exit_code())
        return " ".join(bits) if bits else "clean"

    # ------------------------------------------------------------------
    def to_markdown(self) -> str:
        lines = ["# skill-trigger-lab report", ""]
        lines.append("skill: `%s`  file: `%s`" % (self.skill or "?", self.file or "?"))
        lines.append("")
        if self.error:
            lines.append("**ERROR:** %s" % self.error)
            return "\n".join(lines) + "\n"

        if self.score:
            lines.append("## Routability score: **%d / 100 (grade %s)**" % (
                self.score["points"], self.score["grade"]))
            lines.append("")
            lines.append("> %s" % self.score["note"])
            lines.append("")

        lines.append("## Findings")
        lines.append("")
        if not self.findings:
            lines.append("None — the frontmatter passes all lint rules.")
        else:
            lines.append("| sev | rule | field | problem |")
            lines.append("|---|---|---|---|")
            for f in sorted(self.findings, key=lambda x: SEV_ORDER.get(x.severity, 9)):
                msg = f.message.replace("|", "/").replace("\n", " ")
                if len(msg) > 160:
                    msg = msg[:157] + "..."
                lines.append("| %s %s | `%s` | %s | %s |" % (
                    SEV_ICON.get(f.severity, "?"), f.severity, f.rule, f.field, msg))
        lines.append("")

        if any(f.fix for f in self.findings):
            lines.append("## Suggested fixes")
            lines.append("")
            for f in self.findings:
                if f.fix:
                    lines.append("- **`%s`** — %s" % (f.rule, f.fix))
            lines.append("")

        if self.collisions:
            lines.append("## Trigger collisions (>= threshold overlap)")
            lines.append("")
            lines.append("| other skill | overlap | shared tokens |")
            lines.append("|---|---|---|")
            for c in self.collisions[:10]:
                lines.append("| `%s` | %.2f | %s |" % (
                    c.other, c.score, ", ".join("`%s`" % w for w in c.shared[:8])))
            lines.append("")

        lines.append("## Verdict")
        lines.append("")
        lines.append("`%s` — exit code **%d**. %s" % (
            self.verdict(), self.exit_code(), self.summary_line()))
        return "\n".join(lines) + "\n"
