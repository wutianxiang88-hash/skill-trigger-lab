"""Tolerant parser for SKILL.md YAML frontmatter.

Deliberately NOT a general YAML implementation. It reproduces, on purpose,
the exact behaviours that agentskills-format consumers exhibit so that a lint
run can predict how a host will parse a file:

* a leading byte-order-mark or any line before the opening ``---`` means the
  frontmatter is invisible to strict parsers;
* an unquoted plain scalar containing ``": "`` breaks or truncates the value
  in the sloppy parsers real hosts use;
* folded multi-line values (indented continuation lines) are joined with a
  single space, the way ``js-yaml`` and ``PyYAML`` both do.

Everything here is deterministic and dependency-free so the tool itself can
run in CI.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List, Optional

# 规范上限（agentskills 格式）：name ≤ 64，description ≤ 1024。
NAME_MAX = 64
DESCRIPTION_MAX = 1024
COMPATIBILITY_MAX = 500

# name 合法字符：小写字母、数字、连字符（不允许首尾/连续连字符）。
NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?$")

_FENCE = "---"
_KEY_LINE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:[ \t]+(.*))?$")


@dataclass
class Frontmatter:
    """Result of parsing one SKILL.md.

    ``raw`` keeps the original text so rules can reason about quoting,
    ``present`` says whether a strict host would recognise the block at all,
    and ``truncated_keys`` lists keys whose value strict/sloppy parsers may
    silently cut (unquoted ``": "`` hazard).
    """

    keys: dict = field(default_factory=dict)          # key -> joined value
    raw: dict = field(default_factory=dict)           # key -> first raw value line
    order: List[str] = field(default_factory=list)
    present: bool = False                             # strict parsers see a block
    truncated_keys: List[str] = field(default_factory=list)
    fatal: Optional[str] = None                       # file is unreadable as skill
    body: str = ""


def parse(text: str) -> Frontmatter:
    """Parse frontmatter from *text* (the full SKILL.md contents)."""
    fm = Frontmatter()
    if text.startswith("\ufeff"):
        fm.present = False
        fm.fatal = "leading BOM before the opening '---'"
        return fm

    lines = text.split("\n")

    # 第 1 行必须是 '---'（允许 '\r'）。
    if not lines or lines[0].rstrip("\r") != _FENCE:
        # 若 '---' 出现在更后面，说明 fence 只是位置错了；若全文没有独立
        # fence 行，则是根本没有 frontmatter。两种都是致命伤，但原因不同。
        has_later_fence = any(ln.rstrip("\r") == _FENCE for ln in lines[1:])
        fm.body = text
        fm.present = False
        fm.fatal = ("the opening '---' is not on line 1" if has_later_fence
                    else "no frontmatter block found (missing the opening '---')")
        return fm

    fm.present = True
    closing = None
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r") in (_FENCE, "..."):
            closing = i
            break
    if closing is None:
        fm.fatal = "frontmatter block is never closed by '---'"
        return fm

    fm.body = "\n".join(lines[closing + 1:])

    current: Optional[str] = None
    buf: List[str] = []
    for i in range(1, closing):
        line = lines[i].rstrip("\r")
        if not line.strip():
            if current is not None:
                buf.append("")
            continue
        m = _KEY_LINE.match(line)
        if m and not line[:1].isspace():
            if current is not None:
                _store(fm, current, buf)
            current = m.group(1)
            buf = [m.group(2) or ""]
        elif current is not None:
            buf.append(line.strip())
        else:
            # 顶层非 key 行（如列表项）——宽松宿主直接忽略，记为不可解析。
            fm.fatal = "frontmatter line %d is not a 'key: value' pair" % (i + 1)
            return fm
    if current is not None:
        _store(fm, current, buf)
    return fm


def _store(fm: Frontmatter, key: str, parts: List[str]) -> None:
    raw_first = parts[0] if parts else ""
    value = _unquote(raw_first)
    if len(parts) > 1:
        # 折叠续行：与真实 YAML 行为一致地并回。
        value = _unquote(raw_first, multi=True) + " " + " ".join(
            _strip_cont(p) for p in parts[1:] if p
        )
    value = value.strip()
    fm.keys[key] = value
    fm.raw[key] = raw_first
    fm.order.append(key)
    if _has_plain_colon_space(raw_first):
        fm.truncated_keys.append(key)


def _strip_cont(part: str) -> str:
    return part.strip().strip('"').strip("'")


def _unquote(raw: str, multi: bool = False) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        return raw[1:-1]
    if multi and raw in ("|", ">", "|-", ">-", ">+", "|+"):
        return ""
    return raw


def _has_plain_colon_space(raw: str) -> bool:
    """True if value is unquoted and contains ASCII ': ' — the silent-truncation hazard.

    ``http://`` is safe (no space after colon); ``e.g. use when: fetch`` is not.
    """
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'" :
        return False
    if raw in ("|", ">", "|-", ">-", ">+", "|+"):
        return False
    return ": " in raw


def directory_name(path) -> str:
    """The directory name a SKILL.md lives in (spec: 'name' must match)."""
    p = str(path).rstrip("/")
    parts = p.split("/")
    if parts and parts[-1].lower() == "skill.md":
        parts = parts[:-1]
    return parts[-1] if parts else ""
