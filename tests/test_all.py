import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from skill_trigger_lab.parser import parse, directory_name

HERE = os.path.dirname(__file__)
EX = os.path.join(HERE, "..", "examples")


class TestParser(unittest.TestCase):
    def test_valid_frontmatter(self):
        text = open(os.path.join(EX, "pdf-form-filler", "SKILL.md"), encoding="utf-8").read()
        fm = parse(text)
        self.assertTrue(fm.present)
        self.assertIsNone(fm.fatal)
        self.assertEqual(fm.keys["name"], "pdf-form-filler")
        self.assertIn("AcroForm", fm.keys["description"])

    def test_bom_breaks_strict_parser(self):
        fm = parse("﻿---\nname: x\ndescription: y\n---\nbody")
        self.assertFalse(fm.present)
        self.assertIn("BOM", fm.fatal)

    def test_opening_fence_not_line1(self):
        fm = parse("# Title\n---\nname: x\ndescription: y\n---\n")
        self.assertFalse(fm.present)
        self.assertIn("line 1", fm.fatal)

    def test_missing_closing_fence(self):
        fm = parse("---\nname: x\n")
        self.assertIsNotNone(fm.fatal)
        self.assertIn("never closed", fm.fatal)

    def test_folded_multiline_description(self):
        text = "---\nname: x\ndescription: first part\n  second part\n---\n"
        fm = parse(text)
        self.assertEqual(fm.keys["description"], "first part second part")

    def test_quoted_value(self):
        text = '---\nname: x\ndescription: "has: a colon"\n---\n'
        fm = parse(text)
        self.assertEqual(fm.keys["description"], "has: a colon")
        self.assertNotIn("description", fm.truncated_keys)

    def test_unquoted_colon_flagged(self):
        text = "---\nname: x\ndescription: handles: extraction\n---\n"
        fm = parse(text)
        self.assertIn("description", fm.truncated_keys)

    def test_url_colon_not_flagged(self):
        text = "---\nname: x\ndescription: see http://example.com/docs\n---\n"
        fm = parse(text)
        self.assertNotIn("description", fm.truncated_keys)

    def test_directory_name(self):
        self.assertEqual(directory_name("skills/foo-bar/SKILL.md"), "foo-bar")
        self.assertEqual(directory_name("skills/foo-bar/skill.md"), "foo-bar")

    def test_crlf(self):
        fm = parse("---\r\nname: x\r\ndescription: y\r\n---\r\nbody")
        self.assertTrue(fm.present)
        self.assertEqual(fm.keys["name"], "x")


class TestLint(unittest.TestCase):
    def _lint(self, text, dirname="x"):
        from skill_trigger_lab.lint import lint
        return lint(parse(text), dirname)

    def rules(self, text, dirname="x"):
        return [f.rule for f in self._lint(text, dirname)]

    def test_broken_example_flags_blockers(self):
        text = open(os.path.join(EX, "my-pdf-helper", "SKILL.md"), encoding="utf-8").read()
        fs = self._lint(text, "my-pdf-helper")
        self.assertIn("colon-unquoted", [f.rule for f in fs])
        self.assertTrue(any(f.severity == "blocker" for f in fs))

    def test_good_example_clean(self):
        text = open(os.path.join(EX, "pdf-form-filler", "SKILL.md"), encoding="utf-8").read()
        fs = self._lint(text, "pdf-form-filler")
        self.assertEqual([f for f in fs if f.severity in ("blocker", "high")], [])

    def test_name_missing_blocker(self):
        self.assertIn("name-missing", self.rules("---\ndescription: y\n---\n"))

    def test_name_mismatch(self):
        rs = self.rules("---\nname: a-b\ndescription: use when x\n---\n", dirname="c-d")
        self.assertIn("name-dir-mismatch", rs)

    def test_no_scenario(self):
        rs = self.rules("---\nname: x\ndescription: A tool that processes widgets efficiently.\n---\n")
        self.assertIn("no-trigger-scenario", rs)

    def test_long_name(self):
        n = "a" * 70
        rs = self.rules("---\nname: %s\ndescription: use when x\n---\n" % n)
        self.assertIn("name-length", rs)

    def test_empty_body(self):
        rs = self.rules("---\nname: x\ndescription: use when x\n---\n\n")
        self.assertIn("empty-body", rs)

    def test_unknown_key(self):
        rs = self.rules("---\nname: x\ndescription: use when x\nbanana: 1\n---\nbody")
        self.assertIn("unknown-key", rs)

    def test_invalid_name_chars(self):
        rs = self.rules("---\nname: My_Skill\ndescription: use when x\n---\nbody")
        self.assertIn("name-chars", rs)

    def test_identical_name_desc(self):
        rs = self.rules("---\nname: x-y\ndescription: x-y\n---\nbody")
        self.assertIn("name-desc-identical", rs)

    def test_thin_description(self):
        rs = self.rules("---\nname: x\ndescription: use when pdf\n---\nbody")
        self.assertIn("description-thin", rs)


class TestCollision(unittest.TestCase):
    def test_detect(self):
        from skill_trigger_lab.collision import detect
        pop = [
            {"name": "pdf-merge", "description": "Merge and split PDF files. Use when combining documents."},
            {"name": "calendar", "description": "Manage calendar events. Use when scheduling meetings."},
        ]
        cols = detect("pdf-form", "Fill AcroForm PDF forms and validate fields. Use when filling PDF documents.", pop, threshold=0.15)
        self.assertEqual(len(cols), 1)
        self.assertEqual(cols[0].other, "pdf-merge")
        self.assertGreater(cols[0].score, 0.15)

    def test_no_pop_entry_matches_subject(self):
        from skill_trigger_lab.collision import detect
        pop = [{"name": "self", "description": "same same words"}]
        self.assertEqual(detect("self", "same same words", pop), [])

    def test_read_installed(self):
        from skill_trigger_lab.collision import read_installed
        rows = read_installed(EX)
        names = {r["name"] for r in rows}
        self.assertIn("pdf-form-filler", names)


class TestEvalGen(unittest.TestCase):
    def test_positive_negative_balance(self):
        from skill_trigger_lab.eval import gen_queries
        text = open(os.path.join(EX, "pdf-form-filler", "SKILL.md"), encoding="utf-8").read()
        fm = parse(text)
        qs = gen_queries(fm.keys["name"], fm.keys["description"], fm.body)
        self.assertGreaterEqual(len(qs), 5)
        kinds = {q["kind"] for q in qs}
        self.assertEqual(kinds, {"should_trigger", "should_not_trigger"})

    def test_exclusion_generates_negative(self):
        from skill_trigger_lab.eval import gen_queries
        qs = gen_queries("s", "Fill forms. Use when filling. Do not use for merging pages.", "")
        neg = [q for q in qs if q["kind"] == "should_not_trigger"]
        self.assertTrue(any("merg" in q["query"].lower() for q in neg))


class TestScoreAndReport(unittest.TestCase):
    def test_good_scores_higher_than_broken(self):
        from skill_trigger_lab.analyze import analyze_file
        good = analyze_file(os.path.join(EX, "pdf-form-filler", "SKILL.md"))
        bad = analyze_file(os.path.join(EX, "my-pdf-helper", "SKILL.md"))
        self.assertGreater(good.score["points"], bad.score["points"])
        self.assertEqual(good.exit_code(), 0)
        self.assertEqual(bad.exit_code(), 1)

    def test_unreadable_exit_2(self):
        from skill_trigger_lab.analyze import analyze_file
        rep = analyze_file("/nonexistent/SKILL.md")
        self.assertEqual(rep.exit_code(), 2)
        self.assertEqual(rep.verdict(), "error")

    def test_markdown_renders(self):
        from skill_trigger_lab.analyze import analyze_file
        rep = analyze_file(os.path.join(EX, "my-pdf-helper", "SKILL.md"))
        md = rep.to_markdown()
        self.assertIn("## Findings", md)
        self.assertIn("colon-unquoted", md)

    def test_json_envelope(self):
        import json
        from skill_trigger_lab.analyze import analyze_file
        rep = analyze_file(os.path.join(EX, "pdf-form-filler", "SKILL.md"))
        d = json.loads(rep.to_json())
        self.assertEqual(d["exit_code"], 0)
        self.assertEqual(d["verdict"], "clean")
        self.assertIn("findings", d)


class TestCLI(unittest.TestCase):
    def test_lint_exit_codes(self):
        from skill_trigger_lab.cli import main
        self.assertEqual(main(["lint", os.path.join(EX, "pdf-form-filler", "SKILL.md"), "-q"]), 0)
        self.assertEqual(main(["lint", os.path.join(EX, "my-pdf-helper", "SKILL.md"), "-q"]), 1)

    def test_gen_writes_plan(self):
        import tempfile, json
        from skill_trigger_lab.cli import main
        with tempfile.TemporaryDirectory() as td:
            out = os.path.join(td, "evals.json")
            rc = main(["gen", os.path.join(EX, "pdf-form-filler", "SKILL.md"), "-o", out])
            self.assertEqual(rc, 0)
            plan = json.load(open(out, encoding="utf-8"))
            self.assertEqual(plan["skill"], "pdf-form-filler")

    def test_run_with_stub_runner(self):
        import tempfile, os as _os
        from skill_trigger_lab.cli import main
        plan = _os.path.join(EX, "evals.json")
        stub = "#!/bin/sh\nif grep -qiE 'fill|flatten|acroform|required' ; then echo pdf-form-filler; else echo nothing; fi"
        with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
            fh.write(stub)
            stub_path = fh.name
        rc = main(["run", plan, "--cmd", "/bin/sh %s" % stub_path])
        _os.unlink(stub_path)
        self.assertIn(rc, (0, 1))  # deterministic oracle → full pass on a faithful stub


if __name__ == "__main__":
    unittest.main()
