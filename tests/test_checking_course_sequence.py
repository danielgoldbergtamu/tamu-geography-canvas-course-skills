"""Tests for skills/checking-course-sequence/scripts/check_sequence.py.

Run from the repository root:

    python3 -m unittest discover -s tests -v

The sample course's expected findings are listed in examples/sample-course/PLANTED.md.
Every check is also made to fire on a modified model, so a check that can never fail
cannot pass here.
"""
import copy
import datetime as dt
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/canvas-course-tools/skills"
SAMPLE = ROOT / "examples/sample-course/sample-course.imscc"
AS_OF = dt.date(2026, 9, 1)


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load(SKILLS / "reading-canvas-exports/scripts/read_export.py", "read_export")
seq = load(SKILLS / "checking-course-sequence/scripts/check_sequence.py", "check_sequence")
MODEL = reader.build_model(SAMPLE)


def run(model=None, as_of=AS_OF):
    return seq.Checker(copy.deepcopy(model or MODEL), as_of).run()


def found(checker, severity=None):
    return {(f["check"].split()[0], f["item"]) for f in checker.findings if severity in (None, f["severity"])}


def item(model, title):
    for x in model["assignments"] + model["quizzes"] + model["pages"]:
        if x["title"] == title:
            return x
    raise KeyError(title)


class SampleCourse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = run()

    def test_exact_defects(self):
        self.assertEqual(found(self.c, "defect"), {
            ("1", "Project Proposal"), ("1", "Reading Response 1"), ("2", "Lecture 3: Projections"),
            ("3", "Project Proposal"), ("4", "Participation 1")})

    def test_exact_warnings(self):
        self.assertEqual(found(self.c, "warning"), {("10", "Welcome to SAMP 101")})

    def test_matching_dates_are_not_reported(self):
        self.assertNotIn(("1", "Reading Response 2"), found(self.c))

    def test_correct_patterns_are_not_reported(self):
        self.assertFalse([f for f in self.c.findings if f["check"].startswith("7 ")], "28-day draft gap reported")
        self.assertNotIn(("5", "Instructor Notes"), found(self.c), "unpublished page reported as unreachable")

    def test_every_check_ran(self):
        self.assertEqual(len(self.c.status), 10)
        self.assertFalse([s for s in self.c.status.values() if s.startswith("not run")])


class EachCheckCanFire(unittest.TestCase):
    def test_5_published_orphan(self):
        m = copy.deepcopy(MODEL)
        item(m, "Instructor Notes")["workflow_state"] = "active"
        self.assertIn(("5", "Instructor Notes"), found(run(m), "warning"))

    def test_6_due_long_after_module_week(self):
        m = copy.deepcopy(MODEL)
        a = item(m, "Lab 1: Coordinate Systems")
        a["due_local"] = "2026-09-30T23:59:00-05:00"
        self.assertIn(("6", "Lab 1: Coordinate Systems"), found(run(m), "warning"))

    def test_7_short_revision_gap(self):
        m = copy.deepcopy(MODEL)
        item(m, "Final Project")["due_local"] = "2026-11-18T23:59:00-06:00"
        self.assertIn(("7", "Final Project"), found(run(m), "warning"))

    def test_8_due_on_cancelled_day(self):
        m = copy.deepcopy(MODEL)
        item(m, "Lab 2: Projections")["due_local"] = "2026-09-07T23:59:00-05:00"
        self.assertIn(("8", "Lab 2: Projections"), found(run(m), "info"))

    def test_9_due_soon_and_overdue(self):
        self.assertIn(("9", "Project Draft"), found(run(as_of=dt.date(2026, 11, 8)), "warning"))
        overdue = [f for f in run(as_of=dt.date(2026, 11, 15)).findings if f["item"] == "Project Draft"]
        self.assertTrue(overdue and "never saw it" in overdue[0]["message"])

    def test_4_attendance_is_a_note_not_a_defect(self):
        m = copy.deepcopy(MODEL)
        item(m, "Participation 1")["title"] = "Attendance 1"
        c = run(m)
        self.assertIn(("4", "Attendance 1"), found(c, "info"))
        self.assertNotIn(("4", "Attendance 1"), found(c, "defect"))

    def test_2_dead_assignment_link(self):
        m = copy.deepcopy(MODEL)
        item(m, "Welcome to SAMP 101")["links"].append(
            {"kind": "assignment", "target": "nope", "text": "Lab 9", "tag": "a", "href": "$CANVAS_OBJECT_REFERENCE$/assignments/nope"})
        self.assertIn(("2", "Welcome to SAMP 101"), found(run(m), "defect"))


class WhenFactsAreMissing(unittest.TestCase):
    def test_no_meetings_means_not_run(self):
        m = copy.deepcopy(MODEL)
        m["inferred"]["meetings"]["value"] = None
        m["sessions"] = []
        c = run(m)
        self.assertTrue(c.status["3 Due before taught"].startswith("not run"))
        self.assertTrue(c.status["8 Due on a cancelled class day"].startswith("not run"))
        self.assertIn(("4", "Participation 1"), found(c, "defect"), "other checks must still run")

    def test_no_time_zone_means_date_checks_not_run(self):
        m = copy.deepcopy(MODEL)
        m["inferred"]["time_zone"]["value"] = None
        c = run(m)
        for name in ("1 Date drift", "7 Draft-to-final gap"):
            self.assertTrue(c.status[name].startswith("not run"), name)


class Graph(unittest.TestCase):
    def test_edges(self):
        c = run()
        g = seq.build_graph(MODEL, c)
        edges = {(e["from"], e["to"], e["type"]) for e in g["edges"]}
        proposal = item(MODEL, "Project Proposal")["id"]
        self.assertIn((f"item:{proposal}", "week:3", "due_in_week"), edges)
        self.assertTrue(any(t == "covers_week" and to == "week:4" for _, to, t in edges))
        self.assertTrue(any(t == "contains" and to == f"item:{proposal}" for _, to, t in edges))
        cancelled = [n for n in g["nodes"] if n["type"] == "meeting" and n["cancelled"]]
        self.assertEqual(sorted(n["date"] for n in cancelled), ["2026-09-07", "2026-11-25"])


class CommandLine(unittest.TestCase):
    def test_imscc_in_three_files_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(seq.main([str(SAMPLE), "--out-dir", tmp, "--as-of", "2026-09-01"]), 0)
            for name in ("course_model.json", "sequence_report.md", "sequence_findings.json", "course_graph.json"):
                self.assertTrue((pathlib.Path(tmp) / name).exists(), name)
            report = (pathlib.Path(tmp) / "sequence_report.md").read_text(encoding="utf-8")
            self.assertIn("## Assumptions", report)
            self.assertIn("## Timeline", report)

    def test_fail_on_defect(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(seq.main([str(SAMPLE), "--out-dir", tmp, "--fail-on", "defect"]), 1)

    def test_old_model_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            old = copy.deepcopy(MODEL)
            del old["syllabus"]["links"]
            path = pathlib.Path(tmp) / "course_model.json"
            path.write_text(json.dumps(old), encoding="utf-8")
            self.assertEqual(seq.main([str(path), "--out-dir", tmp]), 2)


if __name__ == "__main__":
    unittest.main()
