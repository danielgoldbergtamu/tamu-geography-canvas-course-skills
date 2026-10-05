#!/usr/bin/env python3
"""Build sample-course.imscc, a small made-up Canvas course used to test every skill.

    python3 examples/sample-course/build_sample_course.py

The course is fictional (SAMP 101) and contains no real people. Its contents and the
defects planted in it are listed in PLANTED.md beside this script; tests assert that
each skill finds exactly those defects.

The output is byte-for-byte reproducible: entries are written in a fixed order with a
fixed timestamp, so rebuilding without changing this script changes nothing.
"""
import pathlib
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
OUT = HERE / "sample-course.imscc"
FIXED_TIME = (1980, 1, 1, 0, 0, 0)
NS = 'xmlns="http://canvas.instructure.com/xsd/cccv1p0"'

# Dates are UTC with no zone marker, as Canvas writes them. The course is in
# US Central time: 04:59 UTC is 11:59 PM CDT before 1 November and 05:59 UTC is
# 11:59 PM CST after it.
ASSIGNMENTS = [
    # id, title, due_at (UTC), points, submission, group, rubric, published
    ("a01", "Reading Response 1", "2026-08-31T04:59:00", 10, "online_text_entry", "gA", "r01", "published"),
    ("a02", "Lab 1: Coordinate Systems", "2026-09-03T04:59:00", 20, "online_upload", "gB", "r02", "published"),
    ("a03", "Reading Response 2", "2026-09-10T04:59:00", 10, "online_text_entry", "gA", "r01", "published"),
    ("a04", "Lab 2: Projections", "2026-09-17T04:59:00", 20, "online_upload", "gB", None, "published"),
    ("a05", "Project Proposal", "2026-09-10T04:59:00", 30, "online_upload", "gC", "r03", "published"),
    ("a06", "Participation 1", "2026-09-24T04:59:00", 5, "none", "gA", None, "published"),
    ("a07", "Project Draft", "2026-11-12T05:59:00", 40, "online_upload", "gC", "r03", "unpublished"),
    ("a08", "Final Project", "2026-12-10T05:59:00", 100, "online_upload", "gC", "r03", "unpublished"),
]
# Assignment bodies. Each carries a known Bloom level (see PLANTED.md); a04 and a06 have
# no usable verb on purpose and must come out "unknown".
INSTRUCTIONS = {
    "a01": "<p>Summarize the reading on coordinate systems in one paragraph.</p>",
    "a02": "<p>Convert ten street addresses to latitude and longitude using the provided tool.</p>",
    "a03": "<p>Explain in your own words why two maps of the same town can disagree.</p>",
    "a05": "<p>Describe the spatial question your project will investigate and the data you will need.</p>",
    "a07": "<p>Analyze your data and break the question into the steps your method will take.</p>",
    "a08": "<p>Evaluate your results and recommend what the client should do next.</p>",
}
GROUPS = [("gA", "Participation", 1, 20.0), ("gB", "Labs", 2, 30.0), ("gC", "Project", 3, 50.0)]
PAGES = [
    ("p01", "welcome", "Welcome to SAMP 101", "active",
     '<p>Start here. This course meets twice a week.</p>'
     '<p>Read <a href="https://canvas.example.edu/courses/12345/pages/study-tips">the study tips page</a> before class.</p>'),
    ("p02", "lecture-1-what-is-a-coordinate", "Lecture 1: What Is a Coordinate?", "active",
     '<p>Latitude, longitude and why a coordinate needs a datum.</p>'
     '<h3>Learning objectives</h3><p>By the end of this lecture you will be able to:</p>'
     '<table><tr><th>Objective</th><th>Outcome</th></tr>'
     '<tr><td>Define latitude and longitude</td><td>CLO1</td></tr>'
     '<tr><td>Explain why a coordinate needs a datum</td><td>CLO1</td></tr></table>'),
    ("p03", "lecture-2-datums", "Lecture 2: Datums", "active", "Datums and why two coordinates for one place can differ."),
    ("p04", "lecture-3-projections", "Lecture 3: Projections", "active",
     '<p>Projections, distortion and choosing a projection for a task.</p>'
     '<h3>Learning objectives</h3><ul><li>Distinguish conformal from equal-area projections</li>'
     '<li>Justify a projection choice for a given task</li></ul>'
     '<img src="$IMS-CC-FILEBASE$/projection.png">'
     '<h4>Further reading</h4>'
     '<p>For the projection table, <a href="https://epsg.org/">click here</a>.</p>'
     '<p><span style="color:#bbbbbb">Grey text that fails contrast.</span></p>'),
    ("p05", "lecture-4-writing-a-proposal", "Lecture 4: Writing a Proposal", "active",
     '<p>How to write a project proposal: question, data, method.</p>'
     '<p>The Project Proposal is due September 16.</p>'),
    ("p06", "instructor-notes", "Instructor Notes", "unpublished", "Not for students."),
]
MODULES = [
    ("m00", "Start Here", [("WikiPage", "p01")]),
    ("m01", "Week 01 — Coordinates", [("WikiPage", "p02"), ("Assignment", "a01"), ("Assignment", "a02")]),
    ("m02", "Week 02 — Datums", [("WikiPage", "p03"), ("Assignment", "a03"), ("DiscussionTopic", "d01")]),
    ("m03", "Week 03 — Projections", [("WikiPage", "p04"), ("Assignment", "a04"), ("Quizzes::Quiz", "q01")]),
    ("m04", "Week 04 — The Project", [("WikiPage", "p05"), ("Assignment", "a05"), ("Assignment", "a06")]),
    ("m05", "Later Weeks", [("Assignment", "a07"), ("Assignment", "a08")]),
]
RUBRICS = [
    ("r01", "Reading Response", False, [
        ("c1", "Summary", 5, None, None), ("c2", "Reflection", 5, None, None),
        ("c3", "Explains a coordinate concept", 0, "o-clo1", None)]),
    ("r02", "Lab", True, [
        ("c1", "Correct output", 10, None, None), ("c2", "Documented steps", 10, None, "9002")]),
    ("r03", "Project", False, [
        ("c1", "Question", 10, "o-clo3", None), ("c2", "Method", 10, None, None), ("c3", "Writing", 10, None, "9001")]),
]
OUTCOMES = [
    ("og1", "Sample Geography BS Program Outcomes", [
        ("o-plo1", "PLO-COMM: Communicates spatial findings", "9001"),
        ("o-plo2", "PLO-METHOD: Applies spatial methods", "9002")]),
    ("og2", "SAMP 101 Course Outcomes", [
        ("o-clo1", "CLO1: Explain coordinate systems", None),
        ("o-clo2", "CLO2: Choose a projection", None),
        ("o-clo3", "CLO3: Frame a spatial question", None)]),
    ("og3", "Other", [("o-x1", "Teamwork", None)]),
]
SYLLABUS = """<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"><title>Syllabus</title></head><body>
<h2>SAMP 101: Sample Course</h2>
<p><strong>Class meetings:</strong> MW 10:00 AM - 11:15 AM, Room 100</p>
<p><strong>Office hours:</strong> Fri 2:00 - 3:00 PM or by appointment</p>
<p>Instructor phone: (555) 010-2030</p>
<h3>Schedule</h3>
<table>
<tr><th>Week</th><th>Monday</th><th>Wednesday</th><th>Due Wednesday</th></tr>
<tr><td>1<br>Aug 24</td><td>Lecture 1</td><td>Lab 1</td><td>Reading Response 1</td></tr>
<tr><td>3<br>Sep 7</td><td>No class — Labor Day</td><td>Lecture 2</td><td>Reading Response 2</td></tr>
<tr><td>14<br>Nov 23</td><td>Project work</td><td>No class — Thanksgiving break</td><td>—</td></tr>
</table>
<p>Final project presentations are held in the last week of classes.</p>
</body></html>
"""


def manifest():
    res = []
    for ident, slug, *_ in PAGES:
        res.append(f'<resource identifier="{ident}" type="webcontent" href="wiki_content/{slug}.html"><file href="wiki_content/{slug}.html"/></resource>')
    for a in ASSIGNMENTS:
        res.append(f'<resource identifier="{a[0]}" type="associatedcontent/imscc_xmlv1p1/learning-application-resource" href="{a[0]}/body.html"><file href="{a[0]}/body.html"/><file href="{a[0]}/assignment_settings.xml"/></resource>')
    res.append('<resource identifier="q01" type="imsqti_xmlv1p2/imscc_xmlv1p1/assessment"><file href="q01/assessment_qti.xml"/><dependency identifierref="q01meta"/></resource>')
    res.append('<resource identifier="q01meta" type="associatedcontent/imscc_xmlv1p1/learning-application-resource" href="q01/assessment_meta.xml"><file href="q01/assessment_meta.xml"/></resource>')
    res.append('<resource identifier="d01" type="imsdt_xmlv1p1"><file href="d01.xml"/></resource>')
    res.append('<resource identifier="d01meta" type="associatedcontent/imscc_xmlv1p1/learning-application-resource" href="d01meta.xml"><file href="d01meta.xml"/><dependency identifierref="d01"/></resource>')
    res.append('<resource identifier="w01" type="imswl_xmlv1p1"><file href="w01.xml"/></resource>')
    res.append('<resource identifier="syl" type="associatedcontent/imscc_xmlv1p1/learning-application-resource" href="course_settings/syllabus.html" intendeduse="syllabus"><file href="course_settings/syllabus.html"/></resource>')
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<manifest identifier="sample" xmlns="http://www.imsglobal.org/xsd/imsccv1p1/imscp_v1p1">'
            '<metadata><schema>IMS Common Cartridge</schema><schemaversion>1.1.0</schemaversion></metadata>'
            '<organizations/><resources>' + "".join(res) + '</resources></manifest>\n')


def files():
    out = {"imsmanifest.xml": manifest()}
    out["course_settings/course_settings.xml"] = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<course identifier="c" {NS}><title>SAMP 101: Sample Course</title>'
        '<course_code>SAMP 101</course_code><start_at>2026-08-24T05:00:00</start_at>'
        '<conclude_at>2027-01-15T06:00:00</conclude_at><default_view>modules</default_view>'
        '<group_weighting_scheme>percent</group_weighting_scheme></course>\n')
    out["course_settings/syllabus.html"] = SYLLABUS
    out["course_settings/assignment_groups.xml"] = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<assignmentGroups {NS}>' + "".join(
            f'<assignmentGroup identifier="{g}"><title>{t}</title><position>{p}</position><group_weight>{w}</group_weight></assignmentGroup>'
            for g, t, p, w in GROUPS) + '</assignmentGroups>\n')
    items = []
    for mi, (mid, title, its) in enumerate(MODULES, 1):
        body = "".join(
            f'<item identifier="{mid}-{n}"><content_type>{ct}</content_type><workflow_state>active</workflow_state>'
            f'<title>{ref}</title><identifierref>{ref}</identifierref><position>{n}</position><indent>0</indent></item>'
            for n, (ct, ref) in enumerate(its, 1))
        items.append(f'<module identifier="{mid}"><title>{title}</title><workflow_state>active</workflow_state>'
                     f'<position>{mi}</position><items>{body}</items></module>')
    out["course_settings/module_meta.xml"] = f'<?xml version="1.0" encoding="UTF-8"?>\n<modules {NS}>' + "".join(items) + '</modules>\n'
    rubrics = []
    for rid, title, free, crits in RUBRICS:
        cs = []
        for cid, desc, pts, olink, oext in crits:
            link = (f"<learning_outcome_identifierref>{olink}</learning_outcome_identifierref><ignore_for_scoring>true</ignore_for_scoring>" if olink
                    else f"<learning_outcome_external_identifier>{oext}</learning_outcome_external_identifier><ignore_for_scoring>false</ignore_for_scoring>" if oext
                    else "<ignore_for_scoring>false</ignore_for_scoring>")
            ratings = "".join(f"<rating><description>{d}</description><points>{p}</points></rating>"
                              for d, p in (("Full", pts), ("Partial", pts / 2), ("None", 0)))
            cs.append(f"<criterion><criterion_id>{cid}</criterion_id><points>{pts}</points><description>{desc}</description>{link}<ratings>{ratings}</ratings></criterion>")
        total = sum(c[2] for c in crits)
        rubrics.append(f'<rubric identifier="{rid}"><title>{title}</title><points_possible>{total}</points_possible>'
                       f'<free_form_criterion_comments>{str(free).lower()}</free_form_criterion_comments><criteria>{"".join(cs)}</criteria></rubric>')
    out["course_settings/rubrics.xml"] = f'<?xml version="1.0" encoding="UTF-8"?>\n<rubrics {NS}>' + "".join(rubrics) + '</rubrics>\n'
    groups = []
    for gid, gtitle, outs in OUTCOMES:
        os_ = "".join(
            f'<learningOutcome identifier="{oid}"><title>{t}</title><description>{t}</description>'
            + (f"<external_identifier>{ext}</external_identifier>" if ext else "")
            + '<is_global_outcome>false</is_global_outcome></learningOutcome>' for oid, t, ext in outs)
        groups.append(f'<learningOutcomeGroup identifier="{gid}"><title>{gtitle}</title><learningOutcomes>{os_}</learningOutcomes></learningOutcomeGroup>')
    out["course_settings/learning_outcomes.xml"] = f'<?xml version="1.0" encoding="UTF-8"?>\n<learningOutcomes {NS}>' + "".join(groups) + '</learningOutcomes>\n'
    for ident, slug, title, state, body in PAGES:
        out[f"wiki_content/{slug}.html"] = (
            f'<html><head><meta http-equiv="Content-Type" content="text/html; charset=utf-8"><title>{title}</title>'
            f'<meta name="identifier" content="{ident}"/><meta name="workflow_state" content="{state}"/></head>'
            f'<body><h2>{title}</h2>{body if body.startswith("<") else "<p>" + body + "</p>"}</body></html>\n')
    for aid, title, due, pts, sub, grp, rub, state in ASSIGNMENTS:
        rubric = (f"<rubric_identifierref>{rub}</rubric_identifierref><rubric_use_for_grading>true</rubric_use_for_grading>" if rub else "")
        out[f"{aid}/assignment_settings.xml"] = (
            f'<?xml version="1.0" encoding="UTF-8"?>\n<assignment identifier="{aid}" {NS}><title>{title}</title>'
            f'<due_at>{due}</due_at><lock_at/><unlock_at/><assignment_group_identifierref>{grp}</assignment_group_identifierref>'
            f'<workflow_state>{state}</workflow_state>{rubric}<points_possible>{pts}</points_possible>'
            f'<grading_type>points</grading_type><submission_types>{sub}</submission_types><peer_reviews>false</peer_reviews></assignment>\n')
        body = INSTRUCTIONS.get(aid, f"<p>Instructions for {title}.</p>")
        out[f"{aid}/body.html"] = f'<html><head><title>{title}</title></head><body>{body}</body></html>\n'
    out["q01/assessment_meta.xml"] = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n<quiz identifier="q01" {NS}><title>Projection Check</title>'
        '<description>&lt;p&gt;Five-minute check on projections.&lt;/p&gt;</description><quiz_type>assignment</quiz_type>'
        '<points_possible>6.0</points_possible><due_at>2026-09-15T04:59:00</due_at>'
        '<assignment_group_identifierref>gB</assignment_group_identifierref><workflow_state>published</workflow_state></quiz>\n')
    out["q01/assessment_qti.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<questestinterop><assessment ident="q01" title="Projection Check"><section ident="root">'
                                     + "".join(f'<item ident="i{n}" title="Q{n}"></item>' for n in (1, 2, 3))
                                     + '</section></assessment></questestinterop>\n')
    out["d01.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<topic xmlns="http://www.imsglobal.org/xsd/imsccv1p1/imsdt_v1p1">'
                      '<title>Which datum does your phone use?</title><text texttype="text/html">&lt;p&gt;Find out and post.&lt;/p&gt;</text></topic>\n')
    out["d01meta.xml"] = (f'<?xml version="1.0" encoding="UTF-8"?>\n<topicMeta identifier="d01meta" {NS}><topic_id>d01</topic_id>'
                          '<title>Which datum does your phone use?</title><type>topic</type><workflow_state>active</workflow_state></topicMeta>\n')
    out["w01.xml"] = ('<?xml version="1.0" encoding="UTF-8"?>\n<webLink xmlns="http://www.imsglobal.org/xsd/imsccv1p1/imswl_v1p1">'
                      '<title>EPSG Registry</title><url href="https://epsg.org/"/></webLink>\n')
    return out


def build(out_path=OUT):
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, body in sorted(files().items()):
            info = zipfile.ZipInfo(name, FIXED_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, body.encode("utf-8"))
    return out_path


if __name__ == "__main__":
    print(f"Wrote {build()}")
