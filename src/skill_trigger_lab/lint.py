"""Deterministic lint rules for SKILL.md frontmatter.

Each rule returns zero or more Findings with a stable id. Rule ids are part
of the output contract (JSON consumers key on them), so renaming one is a
breaking change.

Severity model:
  blocker  — the skill cannot auto-trigger on a spec-compliant host
  high     — likely to break triggering or routing on real hosts
  medium   — measurable routing quality loss (short description, no scenario)
  low      — hygiene / best practice
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from .parser import (
    NAME_MAX,
    DESCRIPTION_MAX,
    COMPATIBILITY_MAX,
    NAME_RE,
    Frontmatter,
)

BLOCKER, HIGH, MEDIUM, LOW = "blocker", "high", "medium", "low"


@dataclass
class Finding:
    rule: str
    severity: str
    field: str
    message: str
    fix: Optional[str] = None

    def to_dict(self):
        d = {"rule": self.rule, "severity": self.severity,
             "field": self.field, "message": self.message}
        if self.fix:
            d["fix"] = self.fix
        return d


# 触发语料里常见的「场景词」。description 至少要命中一个。
SCENARIO_TOKENS = (
    "use when", "use this", "trigger", "also use", "apply when",
    "适用于", "使用当", "当用户", "触发",
)

GENERIC_WORDS = (
    "a skill", "this skill", "helper", "utility", "tool that", "assistant",
    "expert", "guru", "amazing", "powerful", "comprehensive", "seamless",
)


def lint(fm: Frontmatter, dir_name: str) -> List[Finding]:
    out: List[Finding] = []
    add = out.append

    if fm.fatal:
        add(Finding("fm-parse", BLOCKER, "frontmatter",
                    "Frontmatter is not readable by a spec-compliant parser: %s" % fm.fatal,
                    "The file must start with '---' on line 1, then key: value pairs, then a closing '---'."))
        return out

    # R1 name 存在且合法
    name = fm.keys.get("name", "")
    if not name:
        add(Finding("name-missing", BLOCKER, "name",
                    "Missing required key 'name'.",
                    "Add: name: <directory-name>"))
    else:
        if not NAME_RE.match(name):
            add(Finding("name-chars", HIGH, "name",
                        "name '%s' must be lowercase alphanumeric with single hyphens." % name,
                        "Hyphenate it, e.g. my-cool-skill"))
        if len(name) > NAME_MAX:
            add(Finding("name-length", HIGH, "name",
                        "name is %d chars; the spec cap is %d — hosts truncate or reject." % (len(name), NAME_MAX)))
        if dir_name and name != dir_name:
            add(Finding("name-dir-mismatch", HIGH, "name",
                        "name '%s' != directory '%s'. The spec requires them to match; "
                        "several hosts register the skill under the directory and the mismatch "
                        "breaks explicit invocation." % (name, dir_name),
                        "Rename one of them so they are identical."))

    # R2 description 存在 + 长度
    desc = fm.keys.get("description", "")
    if not desc:
        add(Finding("description-missing", BLOCKER, "description",
                    "Missing required key 'description'. Without it the router never surfaces the skill."))
    else:
        if len(desc) > DESCRIPTION_MAX:
            add(Finding("description-too-long", HIGH, "description",
                        "description is %d chars; the spec cap is %d. Trailing text is silently cut by hosts." % (
                            len(desc), DESCRIPTION_MAX)))
        raw_desc = fm.raw.get("description", "")

        # R3 截断坑：值未加引号且含 ': '
        if "description" in fm.truncated_keys:
            add(Finding("colon-unquoted", BLOCKER, "description",
                        "description is unquoted and contains ': ' — YAML consumers treat it as a "
                        "nested mapping and the value is silently truncated at the colon. This is the "
                        "#1 documented cause of 0%% trigger rates.",
                        "Wrap the whole description in double quotes, or rephrase to remove 'word: '."))
        elif "name" in fm.truncated_keys:
            add(Finding("colon-unquoted", HIGH, "name",
                        "name contains ': ' without quotes; quote the value."))

        # R4 触发场景词
        low = desc.lower()
        if not any(tok in low for tok in SCENARIO_TOKENS):
            add(Finding("no-trigger-scenario", MEDIUM, "description",
                        "description states what the skill is but never says WHEN to use it. "
                        "Router selection is driven by the 'Use when…' clause; without it selection "
                        "falls back to keyword luck.",
                        "Append a concrete 'Use when …' clause naming 2–4 real user phrasings."))

        # R5 泛词开头
        head = low[:60]
        for w in GENERIC_WORDS:
            if head.startswith(w):
                add(Finding("generic-opener", LOW, "description",
                            "description opens with generic filler '%s'. First ~60 chars carry the most "
                            "routing weight; lead with the capability." % w))
                break

        # R6 太短（可路由信息量不足）
        if len(desc) < 40:
            add(Finding("description-thin", MEDIUM, "description",
                        "description is only %d chars — too little signal for reliable routing." % len(desc)))

    # R7 未知键（宽松宿主忽略，但 strict 宿主告警）
    known = {"name", "description", "license", "allowed-tools", "compatibility",
             "metadata", "version"}
    for key in fm.order:
        if key not in known:
            add(Finding("unknown-key", LOW, key,
                        "Key '%s' is not in the agentskills spec; some hosts reject the whole file." % key))

    # R8 compatibility 长度
    comp = fm.keys.get("compatibility", "")
    if len(comp) > COMPATIBILITY_MAX:
        add(Finding("compatibility-too-long", MEDIUM, "compatibility",
                    "compatibility exceeds %d chars and will be truncated." % COMPATIBILITY_MAX))

    # R9 正文存在性：frontmatter 外必须有内容
    body = fm.body.strip()
    if not body:
        add(Finding("empty-body", HIGH, "body",
                    "Nothing after the closing '---' — the skill has no instructions."))

    # R10 name 与 description 完全相同（复制粘贴错误）
    if name and desc and name == desc:
        add(Finding("name-desc-identical", MEDIUM, "description",
                    "description is identical to name — it carries zero routing information."))

    return out
