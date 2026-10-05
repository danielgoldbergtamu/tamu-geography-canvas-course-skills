"""Tests for skills/tagging-bloom-levels/scripts/tag_bloom.py.

Run from the repository root:

    python3 -m unittest discover -s tests -v

Expected levels are listed in examples/sample-course/PLANTED.md.
"""
import copy
import csv
import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/canvas-course-tools/skills"
SAMPLE = ROOT / "examples/sample-course/sample-course.imscc"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load(SKILLS / "reading-canvas-exports/scripts/read_export.py", "read_export")
bloom = load(SKILLS / "tagging-bloom-levels/scripts/tag_bloom.py", "tag_bloom")
MODEL = reader.build_model(SAMPLE)


def tag(confirmed=None, model=None):
    return bloom.Tagger(copy.deepcopy(model or MODEL), confirmed).run()


def by_title(t):
    return {r["title"]: r for r in t.rows}


def status(t, outcome_prefix):
    return next(p["status"] for p in t.progressions if p["outcome"].startswith(outcome_prefix))


class SampleLevels(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.t = tag()
        cls.rows = by_title(cls.t)

    def test_known_levels(self):
        expected = {"Reading Response 1": ("Understand", "medium"), "Reading Response 2": ("Understand", "medium"),
                    "Lab 1: Coordinate Systems": ("Apply", "medium"), "Project Proposal": ("Understand", "medium"),
                    "Project Draft": ("Analyze", "medium"), "Final Project": ("Evaluate", "medium"),
                    "Lecture 1: What Is a Coordinate?": ("Understand", "high"),
                    "Lecture 3: Projections": ("Evaluate", "high")}
        for title, (level, conf) in expected.items():
            self.assertEqual((self.rows[title]["proposed_level"], self.rows[title]["confidence"]), (level, conf), title)

    def test_unknowns_are_not_guessed(self):
        unknown = {r["title"] for r in self.t.rows if r["confidence"] == "none" and r["type"] != "page"}
        self.assertEqual(unknown, {"Lecture 2: Datums", "Lecture 4: Writing a Proposal", "Lab 2: Projections",
                                   "Participation 1", "Projection Check", "Which datum does your phone use?"})

    def test_general_pages_are_not_warned_about(self):
        self.assertFalse([f for f in self.t.findings if f[2] == "Welcome to SAMP 101"])

    def test_progressions(self):
        self.assertIn("does not climb", status(self.t, "CLO1"))
        self.assertIn("climbs from Understand to Evaluate", status(self.t, "CLO3"))
        self.assertIn("not measured", status(self.t, "CLO2"))
        self.assertIn("not measured", status(self.t, "Teamwork"))

    def test_lecture_types(self):
        self.assertEqual(self.rows["Lecture 1: What Is a Coordinate?"]["type"], "lecture")
        self.assertEqual(self.rows["Lab 2: Projections"]["type"], "assignment")


class Verbs(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.table, cls.excluded = bloom.load_verbs()

    def test_inflected_heading_is_not_a_verb(self):
        self.assertIsNone(bloom.leading_verb("Named reviewer personas", self.table))
        self.assertEqual(bloom.leading_verb("Name the data your approach depends on", self.table)[0], 1)

    def test_excluded_verbs_carry_no_level(self):
        for line in ("Compare the two projections", "Write a summary", "Map the county", "Check your work"):
            self.assertIsNone(bloom.leading_verb(line, self.table), line)
        self.assertIn("compare", self.excluded)

    def test_objective_preamble_is_skipped(self):
        self.assertEqual(bloom.leading_verb("Students will be able to justify a choice", self.table)[0], 5)

    def test_no_verb_is_listed_twice(self):
        seen = {}
        for level, verb, _ in self.table:
            self.assertNotIn(verb, seen, f"{verb} at levels {seen.get(verb)} and {level}")
            seen[verb] = level
        self.assertFalse(set(seen) & set(self.excluded))


class Confirmation(unittest.TestCase):
    def test_confirmed_level_changes_progression(self):
        rr2 = next(a["id"] for a in MODEL["assignments"] if a["title"] == "Reading Response 2")
        t = tag({rr2: {"confirmed_level": "Analyze", "note": ""}})
        self.assertIn("climbs from Understand to Analyze", status(t, "CLO1"))

    def test_falling_outcome_is_flagged(self):
        final = next(a["id"] for a in MODEL["assignments"] if a["title"] == "Final Project")
        t = tag({final: {"confirmed_level": "Remember", "note": ""}})
        self.assertIn("ends at Remember", status(t, "CLO3"))

    def test_attendance_gets_no_level(self):
        m = copy.deepcopy(MODEL)
        next(a for a in m["assignments"] if a["title"] == "Participation 1")["title"] = "Attendance 1"
        row = by_title(tag(model=m))["Attendance 1"]
        self.assertEqual((row["proposed_level"], row["confidence"]), ("", "not applicable"))


class CommandLine(unittest.TestCase):
    def test_round_trip_keeps_confirmed_levels(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(bloom.main([str(SAMPLE), "--out-dir", tmp]), 0)
            path = pathlib.Path(tmp) / "bloom_levels.csv"
            rows = list(csv.DictReader(path.open(encoding="utf-8")))
            for r in rows:
                if r["title"] == "Lab 2: Projections":
                    r["confirmed_level"] = "Apply"
            with path.open("w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=rows[0].keys())
                w.writeheader()
                w.writerows(rows)
            self.assertEqual(bloom.main([str(SAMPLE), "--out-dir", tmp, "--levels", str(path)]), 0)
            again = {r["title"]: r for r in csv.DictReader(path.open(encoding="utf-8"))}
            self.assertEqual(again["Lab 2: Projections"]["confirmed_level"], "Apply")
            self.assertEqual(again["Lab 1: Coordinate Systems"]["confirmed_level"], "")
            report = (pathlib.Path(tmp) / "bloom_report.md").read_text(encoding="utf-8")
            self.assertIn("Confirmed by the instructor: 1.", report)


if __name__ == "__main__":
    unittest.main()
