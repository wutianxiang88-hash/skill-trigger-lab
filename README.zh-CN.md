# skill-trigger-lab（中文）

**给 agent 技能文件 `SKILL.md` 做静态体检、冲突检测与触发率实测。**

每个技能作者都会撞同一堵墙——装得上，但模型永远不调用它；或者在不该出现的时候乱调用。官方
[anthropics/skills 的评测脚本实测触发率 0%](https://github.com/anthropics/skills/issues/556)，
[claude-code #9716](https://github.com/anthropics/claude-code/issues/9716) 整条 thread 都是「技能不自动激活」。
而绝大多数原因在 frontmatter 里就是确定性的、可离线查出的——不需要烧任何 token。

## 五个它存在的理由

1. **description 未加引号且含 `": "`** —— YAML 消费者把它解析成嵌套映射，description 被静默截断成空值。
   技能从此永不触发，且没有任何报错。（`colon-unquoted`，blocker。这是 0% 触发率的第一大成因）
2. **`name` ≠ 目录名** —— 规范强制相等；按目录注册的宿主里，显式调用直接失效。（`name-dir-mismatch`）
3. **description 没有「Use when …」场景句** —— 路由靠场景语言选择，纯功能清单只能靠关键词碰运气。
4. **frontmatter 根本不存在** —— 开头有 BOM、或 `---` 前有标题行，严格解析器眼里整块都是正文。
5. **触发冲突** —— 两个已装技能描述重叠，互相抢流量。`collision` 子命令给出重叠分数与共享词。

## 用法

```bash
skill-trigger-lab lint my-skill/SKILL.md          # 静态体检，blocker/high 退出码 1，可进 CI
skill-trigger-lab collision my-skill/SKILL.md --installed ~/.claude/skills
skill-trigger-lab gen my-skill/SKILL.md -o evals.json   # 生成种子评测计划（模板派生，需人工润色）
skill-trigger-lab run evals.json --cmd 'claude -p "$(cat)" 2>&1' --marker 'Loaded skills:'
```

Python ≥ 3.9，零依赖，完全离线。

## 诚实边界

- `score` 是**描述质量的启发式分**，不是实测触发率——报告里 JSON 的 `note` 字段明说了这一点。
- `run` 的准确性取决于你的宿主是否真的暴露「技能被加载」的证据；引用准确率时必须同时给出 `--cmd` 和 `--marker`。
- `gen` 生成的是种子查询，不是成品基准。

许可证 MIT · 作者 wutianxiang88-hash
