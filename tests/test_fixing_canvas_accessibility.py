"""Tests for skills/fixing-canvas-accessibility: a11y_html.py, scan_a11y.py and fix_a11y.py.

Run from the repository root:

    python3 -m unittest discover -s tests -v

Expected findings are listed in examples/sample-course/PLANTED.md (cases 12-15 and 19-21).
"""
import contextlib
import hashlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins/canvas-course-tools/skills/fixing-canvas-accessibility/scripts"
SAMPLE = ROOT / "examples/sample-course/sample-course.imscc"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


A = load("a11y_html")
scan = load("scan_a11y")
fixer = load("fix_a11y")


def quiet(fn, *args):
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = fn(list(args))
    return code, out.getvalue() + err.getvalue()


def scan_to(tmp, export=SAMPLE):
    code, _ = quiet(scan.main, str(export), "--out-dir", str(tmp))
    assert code == 0
    return json.loads((pathlib.Path(tmp) / "a11y_plan.json").read_text(encoding="utf-8"))


def filled(plan):
    for f in plan["fixes"]:
        if f["rule"] == "img-alt-missing":
            f["value"] = "World map in the Mercator projection, with Greenland drawn as large as Africa"
        elif f["rule"] == "link-vague":
            f["value"] = "EPSG projection registry"
    return plan


def write(tmp, plan, name="plan.json"):
    path = pathlib.Path(tmp) / name
    path.write_text(json.dumps(plan), encoding="utf-8")
    return path


class SampleScan(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.plan = scan_to(cls.tmp.name)
        cls.report = (pathlib.Path(cls.tmp.name) / "a11y_report.md").read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def rules(self, file):
        return sorted(f["rule"] for f in self.plan["fixes"] if f["file"] == file)

    def test_exact_plants(self):
        self.assertEqual(self.rules("wiki_content/lecture-3-projections.html"),
                         ["contrast", "heading-skip", "img-alt-missing", "link-vague"])
        self.assertEqual(self.rules("wiki_content/welcome.html"),
                         ["iframe-no-title", "table-no-caption", "table-no-header"])
        self.assertEqual(self.rules("course_settings/syllabus.html"), ["table-no-caption"] + ["th-no-scope"] * 4)
        self.assertEqual(len(self.plan["fixes"]), 15)

    def test_statuses_and_values(self):
        by = {(f["file"].split("/")[-1], f["rule"]): f for f in self.plan["fixes"]}
        self.assertEqual(by[("lecture-3-projections.html", "heading-skip")]["value"], "h4")
        self.assertEqual(by[("lecture-3-projections.html", "contrast")]["value"], "#767676")
        self.assertIsNone(by[("lecture-3-projections.html", "img-alt-missing")]["value"])
        self.assertEqual(by[("welcome.html", "iframe-no-title")]["value"], "Embedded content from www.youtube.com")
        self.assertEqual(by[("welcome.html", "table-no-header")]["status"], "proposed")
        self.assertEqual(by[("syllabus.html", "table-no-caption")]["value"], "Schedule")
        self.assertEqual(self.plan["sha256"], hashlib.sha256(SAMPLE.read_bytes()).hexdigest())

    def test_report_lists_what_is_not_checked(self):
        self.assertIn("## Not checked", self.report)
        self.assertIn("discussion", self.report)
        self.assertIn("stylesheets", self.report)

    def test_clean_pages_have_no_findings(self):
        self.assertEqual(self.rules("wiki_content/lecture-2-datums.html"), [])


class FullLoop(unittest.TestCase):
    def test_apply_then_rescan_is_clean_and_deterministic(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = filled(scan_to(tmp))
            path = write(tmp, plan)
            outs = []
            for n in (1, 2):
                out = pathlib.Path(tmp) / f"fixed{n}.imscc"
                code, msg = quiet(fixer.main, str(SAMPLE), str(path), "--apply", "--out", str(out))
                self.assertEqual(code, 0, msg)
                outs.append(out.read_bytes())
            self.assertEqual(outs[0], outs[1])
            rescan = scan_to(pathlib.Path(tmp) / "rescan", pathlib.Path(tmp) / "fixed1.imscc")
            self.assertEqual(rescan["fixes"], [])

    def test_only_planned_files_change_and_surgically(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = filled(scan_to(tmp))
            out = pathlib.Path(tmp) / "fixed.imscc"
            quiet(fixer.main, str(SAMPLE), str(write(tmp, plan)), "--apply", "--out", str(out))
            with zipfile.ZipFile(SAMPLE) as a, zipfile.ZipFile(out) as b:
                self.assertEqual(a.namelist(), b.namelist())
                changed = {n for n in a.namelist() if a.read(n) != b.read(n)}
                self.assertEqual([i.date_time for i in a.infolist()], [i.date_time for i in b.infolist()])
                lec3 = b.read("wiki_content/lecture-3-projections.html").decode()
                old3 = a.read("wiki_content/lecture-3-projections.html").decode()
            self.assertEqual(changed, {f["file"] for f in plan["fixes"]})
            self.assertIn('alt="World map in the Mercator projection', lec3)
            self.assertIn(">EPSG projection registry</a>", lec3)
            self.assertIn("<h4", lec3)
            self.assertNotIn("<h5", lec3)
            self.assertIn("color: #767676", lec3)
            self.assertLess(abs(len(lec3) - len(old3)), 200)

    def test_dry_run_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = filled(scan_to(tmp))
            out = pathlib.Path(tmp) / "fixed.imscc"
            code, msg = quiet(fixer.main, str(SAMPLE), str(write(tmp, plan)), "--out", str(out))
            self.assertEqual(code, 0)
            self.assertIn("Dry run", msg)
            self.assertFalse(out.exists())


class Refusals(unittest.TestCase):
    def test_unfilled_refused_unless_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write(tmp, scan_to(tmp))
            out = pathlib.Path(tmp) / "fixed.imscc"
            code, msg = quiet(fixer.main, str(SAMPLE), str(path), "--apply", "--out", str(out))
            self.assertEqual(code, 2)
            self.assertIn("still need a value", msg)
            code, msg = quiet(fixer.main, str(SAMPLE), str(path), "--apply", "--skip-unfilled", "--out", str(out))
            self.assertEqual(code, 0, msg)
            left = scan_to(pathlib.Path(tmp) / "rescan", out)
            self.assertEqual(sorted(f["rule"] for f in left["fixes"]), ["img-alt-missing", "link-vague"])

    def test_skip_leaves_element(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = filled(scan_to(tmp))
            for f in plan["fixes"]:
                if f["rule"] == "contrast":
                    f["value"] = "skip"
            out = pathlib.Path(tmp) / "fixed.imscc"
            quiet(fixer.main, str(SAMPLE), str(write(tmp, plan)), "--apply", "--out", str(out))
            left = scan_to(pathlib.Path(tmp) / "rescan", out)
            self.assertEqual([f["rule"] for f in left["fixes"]], ["contrast"])

    def test_different_export_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = filled(scan_to(tmp))
            plan["sha256"] = "0" * 64
            code, msg = quiet(fixer.main, str(SAMPLE), str(write(tmp, plan)), "--apply",
                              "--out", str(pathlib.Path(tmp) / "x.imscc"))
            self.assertEqual(code, 2)
            self.assertIn("different export", msg)

    def test_moved_element_refused(self):
        source = '<h3>A</h3><h5 class="x">B</h5>'
        fixes = [f for f in A.check("p.html", source) if f["fix"]]
        self.assertEqual(A.apply(source, fixes), '<h3>A</h3><h4 class="x">B</h4>')
        with self.assertRaises(ValueError):
            A.apply('<h3>A</h3><h5 class="y">B</h5>', fixes)

    def test_overlapping_fixes_refused(self):
        source = "<h2></h2>"
        loc = {"file": "p.html", "tag": "h2", "index": 0, "raw": "<h2>"}
        fixes = [{"fix": "remove", "value": True, "element": loc}, {"fix": "rename", "value": "h3", "element": loc}]
        with self.assertRaises(ValueError):
            A.apply(source, fixes)

    def test_overwrite_original_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            copy = pathlib.Path(tmp) / "c.imscc"
            copy.write_bytes(SAMPLE.read_bytes())
            plan = filled(scan_to(tmp, copy))
            code, msg = quiet(fixer.main, str(copy), str(write(tmp, plan)), "--apply", "--out", str(copy))
            self.assertEqual(code, 2)
            self.assertIn("overwrite", msg)


class Rules(unittest.TestCase):
    def rules(self, source):
        return sorted(f["rule"] for f in A.check("p.html", source))

    def test_contrast_fix_values_pass(self):
        for fg, bg in [("#bbbbbb", "#ffffff"), ("#ff6666", "#ffffff"), ("#555555", "#000000"), ("#88aaff", "#ffffcc")]:
            for target in (4.5, 3.0):
                fixed = A.fix_color(fg, bg, target)
                self.assertGreaterEqual(A.contrast(fixed, bg), target, (fg, bg, target, fixed))
        self.assertEqual(A.fix_color("#bbbbbb", "#ffffff", 4.5), "#767676")

    def test_large_text_uses_three_to_one(self):
        self.assertEqual(self.rules('<p><span style="color:#949494">small</span></p>'), ["contrast"])
        self.assertEqual(self.rules('<p><span style="color:#949494;font-size:18pt">big</span></p>'), [])

    def test_two_fixes_on_one_element_combine(self):
        source = '<h2>A</h2><h4 style="color:#bbbbbb">B</h4>'
        fixes = [f for f in A.check("p.html", source) if f["fix"]]
        self.assertEqual(sorted(f["rule"] for f in fixes), ["contrast", "heading-skip"])
        out = A.apply(source, fixes)
        self.assertTrue(out.startswith('<h2>A</h2><h3 style="color: #'), out)
        self.assertTrue(out.endswith("B</h3>"))
        self.assertEqual(self.rules(out), [])

    def test_link_rules(self):
        self.assertEqual(self.rules('<a href="https://x.org">Read more</a>'), ["link-vague"])
        self.assertEqual(self.rules('<a href="https://x.org">details</a>'), ["link-vague"])
        self.assertEqual(self.rules('<a href="https://x.org">https://x.org</a>'), ["link-bare-url"])
        self.assertEqual(self.rules('<a href="https://x.org"></a>'), ["link-empty"])
        self.assertEqual(self.rules('<a href="https://x.org"><img src="a.png" alt="X home"></a>'), [])
        self.assertEqual(self.rules('<a href="https://x.org">The X registry</a>'), [])

    def test_image_rules(self):
        self.assertEqual(self.rules('<img src="a.png">'), ["img-alt-missing"])
        self.assertEqual(self.rules('<img src="a.png" alt="">'), [])
        self.assertEqual(self.rules('<img src="a.png" alt="a.png">'), ["img-alt-useless"])
        self.assertEqual(self.rules('<img src="a.png" alt="A map of Texas counties">'), [])

    def test_heading_rules(self):
        self.assertEqual(self.rules("<h1>Title</h1>"), ["heading-h1"])
        self.assertEqual(self.rules("<h2></h2>"), ["heading-empty"])
        self.assertEqual(self.rules("<h2>A</h2><h3>B</h3><h2>C</h2>"), [])

    def test_layout_table_can_be_skipped(self):
        source = "<table><tr><td>a</td><td>b</td></tr><tr><td>1</td><td>2</td></tr></table>"
        fixes = [dict(f, value="skip") for f in A.check("p.html", source) if f["rule"] == "table-no-header"]
        self.assertEqual(A.apply(source, fixes), source)


if __name__ == "__main__":
    unittest.main()
