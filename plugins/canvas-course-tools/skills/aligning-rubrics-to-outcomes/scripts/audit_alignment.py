#!/usr/bin/env python3
"""Audit how a Canvas course's rubrics, assignments and learning outcomes connect.

Usage:
    python3 audit_alignment.py course_model.json [--out-dir DIR] [--crosswalk outcome_crosswalk.csv]
    python3 audit_alignment.py COURSE.imscc        [--out-dir DIR]

Reads the course_model.json written by the reading-canvas-exports skill (or runs it on an
.imscc). Writes:

    alignment_report.md        findings, the assignment-to-outcome table, the crosswalk
    alignment_findings.json    the same findings, for other tools
    assignment_outcomes.csv    one row per graded assignment: rubric, points, outcomes
    outcome_crosswalk.csv      course outcome -> program outcome, PROPOSED from the
                               assignments that measure both, with a column the
                               instructor fills in to confirm

Canvas has no field that links a course outcome to a program outcome. The crosswalk is
inferred and every row is a proposal until the instructor confirms it. Pass the CSV back
with --crosswalk to use confirmed rows.

Standard library only. Python 3.10 or later.
"""
import argparse
import csv
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
READER = HERE.parent.parent / "reading-canvas-exports" / "scripts" / "read_export.py"
ATTENDANCE = re.compile(r"\b(attendance|roll\s*call|check[- ]?in)\b", re.I)
SEVERITY = {"defect": 0, "warning": 1, "info": 2}
TOLERANCE = 0.001  # points; anything larger is a real difference in what a student can score
ROUNDING = 0.05    # a gap this small comes from rounding criterion points to two places


class Audit:
    def __init__(self, model, confirmed=None):
        self.m = model
        self.confirmed = confirmed or {}
        self.findings = []
        self.status = {}
        self.outcomes = {o["id"]: o for o in model["outcomes"]}
        self.by_ext = {o["external_identifier"]: o for o in model["outcomes"] if o.get("external_identifier")}
        self.rubrics = {r["id"]: r for r in model["rubrics"]}
        self.graded = [a for a in model["assignments"]
                       if (a.get("points_possible") or 0) > 0 and not a.get("omit_from_final_grade")]

    def add(self, check, severity, subject, message, evidence=""):
        self.findings.append({"check": check, "severity": severity, "subject": subject,
                              "message": message, "evidence": evidence})

    def outcome_for(self, criterion):
        """(outcome, how) for a criterion's link, or (None, why) for a link that resolves to nothing."""
        if criterion.get("outcome"):
            o = self.outcomes.get(criterion["outcome"])
            return (o, "course link") if o else (None, f"links to outcome id {criterion['outcome']}, which is not in the course")
        if criterion.get("outcome_external_id"):
            o = self.by_ext.get(criterion["outcome_external_id"])
            return (o, "institution link") if o else (
                None, f"links to institutional outcome {criterion['outcome_external_id']}, which is not in the course")
        return None, None

    def measured(self, assignment):
        """Outcomes an assignment measures: rubric criteria plus Canvas's own alignment records."""
        found = {}
        rubric = self.rubrics.get(assignment.get("rubric"))
        for c in (rubric or {}).get("criteria", []):
            o, _ = self.outcome_for(c)
            if o:
                found[o["id"]] = o
        for o in self.m["outcomes"]:
            for al in o.get("alignments", []):
                if al.get("content_id") in (assignment["id"], assignment.get("rubric")):
                    found[o["id"]] = o
        return list(found.values())

    # -------------------------------------------------------------- checks
    def run(self):
        name = "1 Graded with no rubric"
        n = 0
        for a in self.graded:
            if ATTENDANCE.search(a["title"] or ""):
                continue
            n += 1
            if not a.get("rubric"):
                self.add(name, "defect", a["title"], f"worth {a['points_possible']:g} points with no rubric attached",
                         "students cannot see how it is graded; outcomes cannot be measured through it")
            elif a["rubric"] not in self.rubrics:
                self.add(name, "defect", a["title"], "names a rubric that is not in the export", a["rubric"])
        self.status[name] = f"run: {n} graded assignments (attendance excluded)"

        name = "2 Rubric not used for grading"
        for a in self.graded:
            if a.get("rubric") in self.rubrics and a.get("rubric_used_for_grading") is False:
                self.add(name, "warning", a["title"], "has a rubric that is not used for grading, so choosing a rating does not set the score",
                         f'rubric "{self.rubrics[a["rubric"]]["title"]}"')
        self.status[name] = "run"

        name = "3 Rubric total and assignment points disagree"
        for a in self.graded:
            r = self.rubrics.get(a.get("rubric"))
            if not r:
                continue
            scored = sum(c.get("points") or 0 for c in r["criteria"] if not c.get("ignore_for_scoring"))
            gap = scored - a["points_possible"]
            if abs(gap) <= TOLERANCE:
                continue
            if abs(gap) <= ROUNDING:
                self.add(name, "warning", a["title"],
                         f"is worth {a['points_possible']:g} points but its rubric's scored criteria add up to {scored:.2f}, "
                         f"so top marks on every criterion give {scored:.2f}; the criterion points were rounded and the "
                         f"remainder was not given to any criterion",
                         f'rubric "{r["title"]}"')
            else:
                self.add(name, "defect", a["title"],
                         f"is worth {a['points_possible']:g} points but its rubric's scored criteria add up to {scored:g}",
                         f'rubric "{r["title"]}"')
        self.status[name] = "run"

        name = "4 Rating levels hidden"
        for r in self.m["rubrics"]:
            if r.get("free_form_criterion_comments"):
                users = [a["title"] for a in self.m["assignments"] if a.get("rubric") == r["id"]]
                self.add(name, "warning", r["title"],
                         "is set to free-form comments, so Canvas shows a comment box instead of the rating levels",
                         f"used by: {', '.join(users) or 'nothing'}")
        self.status[name] = f"run: {len(self.m['rubrics'])} rubrics"

        name = "5 Outcome criterion changes the score"
        for r in self.m["rubrics"]:
            for c in r["criteria"]:
                o, _ = self.outcome_for(c)
                if o and not c.get("ignore_for_scoring") and (c.get("points") or 0) > 0:
                    self.add(name, "warning", r["title"],
                             f'the criterion for outcome "{o["title"]}" counts {c["points"]:g} points toward the score',
                             "an outcome criterion usually records mastery without changing the grade; set it not to count toward the score")
        self.status[name] = "run"

        name = "6 Broken outcome link"
        for r in self.m["rubrics"]:
            for c in r["criteria"]:
                o, why = self.outcome_for(c)
                if o is None and why:
                    self.add(name, "defect", r["title"], f'criterion "{c["description"]}" {why}')
        self.status[name] = "run"

        name = "7 Assignment measures no outcome"
        for a in self.graded:
            if ATTENDANCE.search(a["title"] or "") or not a.get("rubric"):
                continue
            if not self.measured(a):
                self.add(name, "warning", a["title"], "has a rubric, but no criterion is linked to any learning outcome")
        self.status[name] = "run"

        name = "8 Outcome not measured"
        for o in self.m["outcomes"]:
            users = [a for a in self.graded if any(x["id"] == o["id"] for x in self.measured(a))]
            if not users:
                self.add(name, "warning", o["title"], f"is an outcome of {o.get('level', 'unknown')} level that no graded assignment measures")
        self.status[name] = f"run: {len(self.m['outcomes'])} outcomes"

        name = "9 Rating levels have no descriptions"
        for r in self.m["rubrics"]:
            bare = [c["description"] for c in r["criteria"] if c.get("ratings")
                    and not any((x.get("long_description") or "").strip() for x in c["ratings"])
                    and not self.outcome_for(c)[0]]
            if bare and len(bare) == len([c for c in r["criteria"] if not self.outcome_for(c)[0]]):
                self.add(name, "info", r["title"], "no rating level says what earns it; students see only the level names and points",
                         f"criteria: {', '.join(bare)}")
        self.status[name] = "run"

        self.crosswalk()
        self.findings.sort(key=lambda f: (SEVERITY[f["severity"]], int(f["check"].split()[0]), f["subject"] or ""))
        for i, f in enumerate(self.findings, 1):
            f["id"] = f"A{i}"
        return self

    def crosswalk(self):
        """Propose course -> program links from assignments that measure both."""
        course = [o for o in self.m["outcomes"] if o.get("level") == "course"]
        program = [o for o in self.m["outcomes"] if o.get("level") == "program"]
        self.rows = []
        for c in course:
            linked = False
            for p in program:
                both = [a["title"] for a in self.graded
                        if {c["id"], p["id"]} <= {x["id"] for x in self.measured(a)}]
                key = (c["title"], p["title"])
                conf = self.confirmed.get(key, {}).get("confirmed", "")
                if both or conf:
                    linked = linked or bool(both) or conf.lower() in ("yes", "y")
                    self.rows.append({"course_outcome": c["title"], "program_outcome": p["title"],
                                      "assignments_measuring_both": len(both), "evidence": "; ".join(both),
                                      "proposed": "yes" if both else "no", "confirmed": conf})
            if not linked:
                self.rows.append({"course_outcome": c["title"], "program_outcome": "", "assignments_measuring_both": 0,
                                  "evidence": "", "proposed": "no program outcome is measured alongside it", "confirmed": ""})
                self.add("10 Course outcome rolls up to nothing", "warning", c["title"],
                         "no assignment measures it together with a program outcome, so no roll-up can be proposed; the instructor must say which program outcome it serves, if any")
        unknown = [o["title"] for o in self.m["outcomes"] if o.get("level") == "unknown"]
        if unknown:
            self.add("10 Course outcome rolls up to nothing", "info", None,
                     f"{len(unknown)} outcome(s) could not be classed as course or program level, so they are left out of the crosswalk",
                     ", ".join(unknown))
        self.status["10 Course outcome rolls up to nothing"] = f"run: {len(course)} course and {len(program)} program outcomes"


def write_csv(path, rows, cols):
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def report(model, a):
    sev = {k: sum(f["severity"] == k for f in a.findings) for k in SEVERITY}
    out = [f"# Rubrics and outcomes: {model['course']['title'] or model['source']['file']}", "",
           f"{len(a.graded)} graded assignments, {len(model['rubrics'])} rubrics, {len(model['outcomes'])} outcomes "
           f"({sum(o.get('level') == 'course' for o in model['outcomes'])} course level, "
           f"{sum(o.get('level') == 'program' for o in model['outcomes'])} program level). "
           f"{sev['defect']} defects, {sev['warning']} warnings, {sev['info']} notes.", "",
           "## Outcome levels", "",
           "Canvas does not mark an outcome as course or program level. Each outcome's level was inferred:", ""]
    for o in model["outcomes"]:
        out.append(f"- **{o['title']}:** {o.get('level')} ({o.get('level_source', '')})")
    out += ["", "## Checks", "", "| # | Check | Result |", "|---|---|---|"]
    for name in sorted(a.status, key=lambda n: int(n.split()[0])):
        n, title = name.split(" ", 1)
        out.append(f"| {n} | {title} | {a.status[name]}; {sum(f['check'] == name for f in a.findings)} finding(s) |")
    out += ["", "## Findings", ""]
    for f in a.findings:
        out.append(f"{f['id']}. **{f['severity'].capitalize()}, check {f['check'].split()[0]}.** "
                   f"{f['subject'] or 'Course'}: {f['message']}." + (f" Evidence: {f['evidence']}" if f['evidence'] else ""))
    if not a.findings:
        out.append("No findings.")
    out += ["", "## What each graded assignment measures", "", "| Assignment | Points | Rubric | Outcomes |", "|---|---|---|---|"]
    for x in sorted(a.graded, key=lambda x: (x.get("due_local") or "9", x["title"])):
        r = a.rubrics.get(x.get("rubric"))
        out.append(f"| {x['title']} | {x['points_possible']:g} | {r['title'] if r else '—'} | "
                   f"{', '.join(o['title'] for o in a.measured(x)) or '—'} |")
    out += ["", "## Proposed course-to-program crosswalk", "",
            "A course outcome is proposed to serve a program outcome when at least one graded assignment measures both. "
            "**Every row is a proposal.** Confirm or reject each one in the `confirmed` column of `outcome_crosswalk.csv` "
            "(yes or no) and run again with `--crosswalk outcome_crosswalk.csv`.", "",
            "| Course outcome | Program outcome | Assignments measuring both | Confirmed |", "|---|---|---|---|"]
    for r in a.rows:
        out.append(f"| {r['course_outcome']} | {r['program_outcome'] or '— (none proposed)'} | "
                   f"{r['assignments_measuring_both'] or '—'} | {r['confirmed'] or '—'} |")
    out += ["", "## What this does not check", "",
            "- Whether a rubric's criteria actually assess what its outcome describes. That needs a person reading both.",
            "- New Quizzes and their outcome alignments, which Canvas exports separately.",
            "- Outcomes aligned at the account level but never imported into the course.", ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Audit rubrics, assignments and learning outcomes")
    ap.add_argument("input", help="course_model.json, or a .imscc export")
    ap.add_argument("--out-dir", help="where to write the outputs (default: beside the input)")
    ap.add_argument("--crosswalk", help="an outcome_crosswalk.csv with the confirmed column filled in")
    args = ap.parse_args(argv)
    src = pathlib.Path(args.input)
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else src.resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".imscc":
        if not READER.exists():
            print("error: given an .imscc, but the reading-canvas-exports skill is not installed beside this one.", file=sys.stderr)
            return 2
        model_path = out_dir / "course_model.json"
        done = subprocess.run([sys.executable, str(READER), str(src), "--out", str(model_path)])
        if done.returncode:
            return done.returncode
        src = model_path
    try:
        model = json.loads(src.read_text(encoding="utf-8"))
        confirmed = {}
        if args.crosswalk:
            with open(args.crosswalk, newline="", encoding="utf-8") as fh:
                confirmed = {(r["course_outcome"], r["program_outcome"]): r for r in csv.DictReader(fh)}
    except (OSError, json.JSONDecodeError, csv.Error, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    a = Audit(model, confirmed).run()
    write_csv(out_dir / "outcome_crosswalk.csv", a.rows,
              ["course_outcome", "program_outcome", "assignments_measuring_both", "evidence", "proposed", "confirmed"])
    write_csv(out_dir / "assignment_outcomes.csv",
              [{"assignment_id": x["id"], "assignment": x["title"], "points": x["points_possible"],
                "rubric_id": x.get("rubric") or "", "rubric": (a.rubrics.get(x.get("rubric")) or {}).get("title", ""),
                "outcomes": "; ".join(o["title"] for o in a.measured(x))} for x in a.graded],
              ["assignment_id", "assignment", "points", "rubric_id", "rubric", "outcomes"])
    (out_dir / "alignment_findings.json").write_text(json.dumps(
        {"status": a.status, "findings": a.findings, "crosswalk": a.rows}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "alignment_report.md").write_text(report(model, a), encoding="utf-8")
    sev = {k: sum(f["severity"] == k for f in a.findings) for k in SEVERITY}
    print(f"{sev['defect']} defects, {sev['warning']} warnings, {sev['info']} notes")
    print(f"Wrote {out_dir / 'alignment_report.md'}, alignment_findings.json, assignment_outcomes.csv and outcome_crosswalk.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
