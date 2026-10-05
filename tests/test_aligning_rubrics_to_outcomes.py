"""Tests for skills/aligning-rubrics-to-outcomes: audit_alignment.py and write_rubrics.py.

Run from the repository root:

    python3 -m unittest discover -s tests -v

Expected findings are listed in examples/sample-course/PLANTED.md (cases 2-5 and 16-18).
"""
import copy
import importlib.util
import json
import pathlib
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SKILLS = ROOT / "plugins/canvas-course-tools/skills"
SAMPLE = ROOT / "examples/sample-course/sample-course.imscc"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load(SKILLS / "reading-canvas-exports/scripts/read_export.py", "read_export")
audit = load(SKILLS / "aligning-rubrics-to-outcomes/scripts/audit_alignment.py", "audit_alignment")
writer = load(SKILLS / "aligning-rubrics-to-outcomes/scripts/write_rubrics.py", "write_rubrics")
MODEL = reader.build_model(SAMPLE)

PLAN = {
    "create": [{"assignment_id": "a04", "title": "Lab 2 rubric", "outcomes": ["o-clo2"], "criteria": [
        {"description": "Correct projection chosen", "points": 10, "ratings": [
            {"description": "Full", "long_description": "Says why.", "points": 10},
            {"description": "None", "long_description": "Unsuitable.", "points": 0}]},
        {"description": "Distortion explained", "points": 10, "ratings": [
            {"description": "Full", "long_description": "Locates it.", "points": 10},
            {"description": "None", "long_description": "Absent.", "points": 0}]}]}],
    "show_rating_levels": ["r02"],
    "add_outcomes": [{"rubric_id": "r01", "outcome": "9002"}],
}


def run(model=None):
    return audit.Audit(copy.deepcopy(model or MODEL)).run()


def found(a, severity=None):
    return {(f["check"].split()[0], f["subject"]) for f in a.findings if severity in (None, f["severity"])}


class Audit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.a = run()

    def test_exact_defects(self):
        self.assertEqual(found(self.a, "defect"), {
            ("1", "Lab 2: Projections"), ("1", "Participation 1"),
            ("3", "Project Proposal"), ("3", "Project Draft"), ("3", "Final Project")})

    def test_exact_warnings(self):
        self.assertEqual(found(self.a, "warning"), {
            ("4", "Lab"), ("5", "Lab"), ("5", "Project"),
            ("8", "CLO2: Choose a projection"), ("8", "Teamwork"),
            ("10", "CLO1: Explain coordinate systems"), ("10", "CLO2: Choose a projection")})

    def test_crosswalk_is_proposed_not_reported(self):
        row = [r for r in self.a.rows if r["course_outcome"].startswith("CLO3")]
        self.assertEqual([(r["program_outcome"], r["assignments_measuring_both"]) for r in row],
                         [("PLO-COMM: Communicates spatial findings", 3)])
        self.assertNotIn(("10", "CLO3: Frame a spatial question"), found(self.a))

    def test_correct_outcome_criterion_is_not_reported(self):
        # The Reading Response rubric's CLO1 criterion is worth 0 and does not count.
        self.assertNotIn(("5", "Reading Response"), found(self.a))

    def test_rounding_gap_is_a_warning_and_a_real_gap_a_defect(self):
        for delta, severity in ((0.01, "warning"), (1.0, "defect")):
            m = copy.deepcopy(MODEL)
            lab = next(r for r in m["rubrics"] if r["title"] == "Lab")
            lab["criteria"][0]["points"] += delta
            self.assertIn(("3", "Lab 1: Coordinate Systems"), found(run(m), severity), delta)

    def test_not_used_for_grading_fires(self):
        m = copy.deepcopy(MODEL)
        next(x for x in m["assignments"] if x["title"] == "Lab 1: Coordinate Systems")["rubric_used_for_grading"] = False
        self.assertIn(("2", "Lab 1: Coordinate Systems"), found(run(m), "warning"))

    def test_broken_outcome_link_fires(self):
        m = copy.deepcopy(MODEL)
        m["rubrics"][0]["criteria"][0]["outcome"] = "missing"
        self.assertIn(("6", m["rubrics"][0]["title"]), found(run(m), "defect"))

    def test_confirmed_crosswalk_is_kept(self):
        a = audit.Audit(copy.deepcopy(MODEL), {("CLO1: Explain coordinate systems", "PLO-COMM: Communicates spatial findings"):
                                               {"confirmed": "yes"}}).run()
        self.assertNotIn(("10", "CLO1: Explain coordinate systems"), found(a))


class Writer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = pathlib.Path(self.tmp.name) / "course.imscc"
        self.src.write_bytes(SAMPLE.read_bytes())
        self.plan = pathlib.Path(self.tmp.name) / "plan.json"
        self.plan.write_text(json.dumps(PLAN), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_tracked_sandbox_demo_matches_a_fresh_run(self):
        demo = ROOT / "examples/sample-course"
        fresh = pathlib.Path(self.tmp.name) / "fresh.imscc"
        self.assertEqual(writer.main([str(demo / "sample-course.imscc"), str(demo / "rubric_plan.json"),
                                      "--apply", "--out", str(fresh)]), 0)
        self.assertEqual(fresh.read_bytes(), (demo / "sample-course.rubrics.imscc").read_bytes(),
                         "sample-course.rubrics.imscc is stale: rerun write_rubrics.py with rubric_plan.json")

    def test_dry_run_writes_nothing(self):
        self.assertEqual(writer.main([str(self.src), str(self.plan)]), 0)
        self.assertFalse((pathlib.Path(self.tmp.name) / "course.rubrics.imscc").exists())

    def test_apply_fixes_exactly_what_the_plan_targets(self):
        self.assertEqual(writer.main([str(self.src), str(self.plan), "--apply"]), 0)
        out = pathlib.Path(self.tmp.name) / "course.rubrics.imscc"
        self.assertEqual(self.src.read_bytes(), SAMPLE.read_bytes(), "original export was modified")
        with zipfile.ZipFile(out) as zf:
            ET.fromstring(zf.read("course_settings/rubrics.xml"))  # well-formed
            settings = zf.read("a04/assignment_settings.xml").decode()
        self.assertIn("<rubric_use_for_grading>true</rubric_use_for_grading>", settings)
        before, after = found(run()), found(run(reader.build_model(out)))
        self.assertEqual(before - after, {("1", "Lab 2: Projections"), ("4", "Lab"),
                                          ("8", "CLO2: Choose a projection"), ("10", "CLO1: Explain coordinate systems")})
        self.assertEqual(after - before, set(), "the plan introduced new findings")

    def test_points_must_add_up(self):
        bad = copy.deepcopy(PLAN)
        bad["create"][0]["criteria"][1]["points"] = 5
        bad["create"][0]["criteria"][1]["ratings"][0]["points"] = 5
        self.plan.write_text(json.dumps(bad), encoding="utf-8")
        self.assertEqual(writer.main([str(self.src), str(self.plan), "--apply"]), 2)
        self.assertFalse((pathlib.Path(self.tmp.name) / "course.rubrics.imscc").exists())

    def test_unknown_outcome_and_existing_rubric_are_refused(self):
        for plan in ({"add_outcomes": [{"rubric_id": "r01", "outcome": "NOPE"}]},
                     {"create": [{"assignment_id": "a01", "criteria": []}]},
                     {"show_rating_levels": ["r01"]},
                     {}):
            self.plan.write_text(json.dumps(plan), encoding="utf-8")
            self.assertEqual(writer.main([str(self.src), str(self.plan)]), 2, plan)

    def test_rubrics_file_is_added_to_the_manifest_when_missing(self):
        files = {}
        with zipfile.ZipFile(SAMPLE) as zf:
            for n in zf.namelist():
                if n != "course_settings/rubrics.xml":
                    files[n] = zf.read(n)
        files["imsmanifest.xml"] = files["imsmanifest.xml"].replace(
            b"<resources>", b'<resources><resource identifier="cs" type="associatedcontent/imscc_xmlv1p1/learning-application-resource">'
                            b'<file href="course_settings/course_settings.xml"/></resource>', 1)
        bare = pathlib.Path(self.tmp.name) / "bare.imscc"
        with zipfile.ZipFile(bare, "w") as zf:
            for n, b in files.items():
                zf.writestr(n, b)
        only_create = {"create": PLAN["create"]}
        self.plan.write_text(json.dumps(only_create), encoding="utf-8")
        self.assertEqual(writer.main([str(bare), str(self.plan), "--apply"]), 0)
        with zipfile.ZipFile(pathlib.Path(self.tmp.name) / "bare.rubrics.imscc") as zf:
            self.assertIn(b'href="course_settings/rubrics.xml"', zf.read("imsmanifest.xml"))
            ET.fromstring(zf.read("course_settings/rubrics.xml"))


if __name__ == "__main__":
    unittest.main()
