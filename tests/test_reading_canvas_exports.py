"""Tests for skills/reading-canvas-exports/scripts/read_export.py.

Run from the repository root:

    python3 -m unittest discover -s tests -v

Expected values come from examples/sample-course/PLANTED.md. Each inference is tested
in both directions: that it finds what is there, and that it does not invent what is not.
"""
import importlib.util
import json
import pathlib
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
READER = ROOT / "plugins/canvas-course-tools/skills/reading-canvas-exports/scripts/read_export.py"
SAMPLE_BUILDER = ROOT / "examples/sample-course/build_sample_course.py"
SAMPLE = ROOT / "examples/sample-course/sample-course.imscc"


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reader = load(READER, "read_export")
builder = load(SAMPLE_BUILDER, "build_sample_course")


def sample_with(tmp, **replace):
    """Build the sample course, then replace whole files inside it."""
    path = pathlib.Path(tmp) / "variant.imscc"
    files = builder.files()
    files.update(replace)
    with zipfile.ZipFile(path, "w") as zf:
        for name, body in sorted(files.items()):
            if body is not None:
                zf.writestr(name, body)
    return path


class SampleCourse(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.model = reader.build_model(SAMPLE)

    def test_tracked_sample_matches_a_fresh_build(self):
        with tempfile.TemporaryDirectory() as tmp:
            fresh = builder.build(pathlib.Path(tmp) / "fresh.imscc")
            self.assertEqual(fresh.read_bytes(), SAMPLE.read_bytes(),
                             "sample-course.imscc is stale: run examples/sample-course/build_sample_course.py")

    def test_counts(self):
        m = self.model
        self.assertEqual((len(m["modules"]), len(m["pages"]), len(m["assignments"]), len(m["quizzes"]),
                          len(m["discussions"]), len(m["rubrics"]), len(m["outcomes"])), (6, 6, 8, 1, 1, 3, 6))

    def test_time_zone(self):
        tz = self.model["inferred"]["time_zone"]
        self.assertEqual((tz["value"], tz["confidence"]), ("America/Chicago", "high"))

    def test_local_times_follow_daylight_saving(self):
        due = {a["title"]: a["due_local"] for a in self.model["assignments"]}
        self.assertEqual(due["Participation 1"], "2026-09-23T23:59:00-05:00")
        self.assertEqual(due["Project Draft"], "2026-11-11T23:59:00-06:00")

    def test_meetings_ignore_office_hours_and_phone_numbers(self):
        meet = self.model["inferred"]["meetings"]
        self.assertEqual(meet["value"], {"days": ["Mon", "Wed"], "start": "10:00", "end": "11:15"})
        self.assertEqual(meet["confidence"], "high")
        self.assertIn("Office hours", meet["evidence"])

    def test_cancelled_meetings(self):
        cancelled = [s["date"] for s in self.model["sessions"] if s["cancelled"]]
        self.assertEqual(cancelled, ["2026-09-07", "2026-11-25"])
        self.assertTrue(all(s["weekday"] in ("Mon", "Wed") for s in self.model["sessions"]))

    def test_term_end_ignores_padded_course_end_date(self):
        self.assertEqual(self.model["inferred"]["term_end"]["value"], "2026-12-09")

    def test_outcome_levels_are_not_guessed(self):
        levels = {o["title"].split(":")[0]: o["level"] for o in self.model["outcomes"]}
        self.assertEqual(levels, {"PLO-COMM": "program", "PLO-METHOD": "program", "CLO1": "course",
                                  "CLO2": "course", "CLO3": "course", "Teamwork": "unknown"})

    def test_rubric_outcome_links(self):
        crits = {(r["title"], c["description"]): c for r in self.model["rubrics"] for c in r["criteria"]}
        self.assertEqual(crits[("Reading Response", "Explains a coordinate concept")]["outcome"], "o-clo1")
        self.assertEqual(crits[("Project", "Writing")]["outcome_external_id"], "9001")
        self.assertTrue([r for r in self.model["rubrics"] if r["title"] == "Lab"][0]["free_form_criterion_comments"])

    def test_discussion_and_quiz(self):
        self.assertEqual(self.model["discussions"][0]["title"], "Which datum does your phone use?")
        self.assertEqual(self.model["quizzes"][0]["question_count"], 3)

    def test_writes_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "course_model.json"
            self.assertEqual(reader.main([str(SAMPLE), "--out", str(out)]), 0)
            self.assertEqual(json.loads(out.read_text(encoding="utf-8"))["schema_version"], reader.SCHEMA_VERSION)


class TimeZoneFallback(unittest.TestCase):
    """The rules used when Python has no time-zone database, as on Windows by default."""

    def test_fallback_matches_the_database_every_hour(self):
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo("America/Chicago")
        except Exception:
            self.skipTest("no time-zone database to compare against on this computer")
        import datetime as dt
        for name, (std, rule) in reader._RULES.items():
            fallback, real = reader._RuleZone(name, std, rule), ZoneInfo(name)
            t = dt.datetime(2025, 1, 1, tzinfo=dt.timezone.utc)
            while t < dt.datetime(2028, 1, 1, tzinfo=dt.timezone.utc):
                a, b = t.astimezone(fallback), t.astimezone(real)
                self.assertEqual((a.replace(tzinfo=None), a.utcoffset()), (b.replace(tzinfo=None), b.utcoffset()),
                                 f"{name} at {t.isoformat()}")
                self.assertEqual(a.astimezone(dt.timezone.utc), t)
                t += dt.timedelta(hours=1)

    def test_sample_course_infers_chicago_without_a_database(self):
        original = reader.zone

        def no_database(name):
            return reader._RuleZone(name, *reader._RULES[name]) if name in reader._RULES else None

        reader.zone = no_database
        try:
            m = reader.build_model(SAMPLE)
        finally:
            reader.zone = original
        self.assertEqual(m["inferred"]["time_zone"]["value"], "America/Chicago")
        due = {a["title"]: a["due_local"] for a in m["assignments"]}
        self.assertEqual(due["Project Draft"], "2026-11-11T23:59:00-06:00")


class WhatIsNotThere(unittest.TestCase):
    def test_not_a_zip(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = pathlib.Path(tmp) / "course.imscc"
            bad.write_text("not a zip")
            with self.assertRaisesRegex(reader.ExportError, "not a zip"):
                reader.build_model(bad)

    def test_zip_without_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = sample_with(tmp, **{"imsmanifest.xml": None})
            with self.assertRaisesRegex(reader.ExportError, "imsmanifest.xml"):
                reader.build_model(path)

    def test_office_hours_only_gives_no_meetings(self):
        syllabus = "<html><body><p>Office hours: Tues 11:00 AM - 12:00 PM</p></body></html>"
        with tempfile.TemporaryDirectory() as tmp:
            m = reader.build_model(sample_with(tmp, **{"course_settings/syllabus.html": syllabus}))
        self.assertIsNone(m["inferred"]["meetings"]["value"])
        self.assertEqual(m["sessions"], [])
        self.assertTrue(any("meeting pattern could not be inferred" in w for w in m["warnings"]))

    def test_no_times_at_all(self):
        with tempfile.TemporaryDirectory() as tmp:
            m = reader.build_model(sample_with(tmp, **{"course_settings/syllabus.html": "<p>Welcome.</p>"}))
        self.assertIsNone(m["inferred"]["meetings"]["value"])
        self.assertIn("no days with a time range", m["inferred"]["meetings"]["reason"])

    def test_no_cancellations_is_said_out_loud(self):
        syllabus = "<p>Class meets MW 10:00 AM - 11:15 AM.</p>"
        with tempfile.TemporaryDirectory() as tmp:
            m = reader.build_model(sample_with(tmp, **{"course_settings/syllabus.html": syllabus}))
        self.assertFalse(any(s["cancelled"] for s in m["sessions"]))
        self.assertTrue(any("no cancelled class meetings" in w for w in m["warnings"]))

    def test_settings_file_overrides_inference(self):
        overrides = {"time_zone": "America/Denver",
                     "meetings": {"days": ["Tue"], "start": "09:00", "end": "10:00"},
                     "cancelled": []}
        m = reader.build_model(SAMPLE, overrides)
        self.assertEqual(m["inferred"]["time_zone"]["source"], "settings file")
        self.assertTrue(all(s["weekday"] == "Tue" for s in m["sessions"]))
        self.assertFalse(any(s["cancelled"] for s in m["sessions"]))


if __name__ == "__main__":
    unittest.main()
