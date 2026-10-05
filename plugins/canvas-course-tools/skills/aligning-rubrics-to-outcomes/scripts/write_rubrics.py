#!/usr/bin/env python3
"""Write reviewed rubrics and outcome links into a copy of a Canvas export.

Usage:
    python3 write_rubrics.py COURSE.imscc rubric_plan.json             # dry run: show every change
    python3 write_rubrics.py COURSE.imscc rubric_plan.json --apply     # write COURSE.rubrics.imscc

The original export is never modified. The output is a new .imscc beside it (or --out).

The plan is a JSON file; its format is in references/rubric-plan.md. It can:
  - create a rubric and attach it to an assignment, used for grading;
  - add an outcome criterion to an existing or new rubric, not counted toward the score;
  - turn on rating levels for a rubric that shows only a comment box;
  - turn on "use for grading" for an attached rubric.

Before writing anything it refuses a plan that names an assignment, rubric or outcome the
export does not contain, or whose scored criteria do not add up to the assignment's points.

The XML written here copies what Canvas itself writes in a course export: a course
outcome is linked by learning_outcome_identifierref, an institutional one by
learning_outcome_external_identifier, and an outcome criterion uses the outcome's own
mastery scale. Standard library only. Python 3.10 or later.
"""
import argparse
import hashlib
import html
import json
import pathlib
import re
import sys
import zipfile

CANVAS_NS = 'xmlns="http://canvas.instructure.com/xsd/cccv1p0" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="http://canvas.instructure.com/xsd/cccv1p0 https://canvas.instructure.com/xsd/cccv1p0.xsd"'
# Canvas's default outcome scale, used when an outcome in the export carries no ratings.
DEFAULT_MASTERY = [("Exceeds Mastery", 4.0), ("Mastery", 3.0), ("Near Mastery", 2.0), ("Below Mastery", 1.0), ("No Evidence", 0.0)]
TOLERANCE = 0.01


class PlanError(Exception):
    """The plan cannot be applied. The message says what to fix."""


def ident(*parts):
    """A stable Canvas-style identifier: 'g' and 32 hex digits, derived from its inputs."""
    return "g" + hashlib.md5("|".join(parts).encode("utf-8")).hexdigest()


def esc(text):
    return html.escape(str(text or ""), quote=False)


def tag(xml, name):
    m = re.search(rf"<{name}>(.*?)</{name}>", xml, re.S)
    return html.unescape(m.group(1)) if m else None


class Export:
    def __init__(self, path):
        self.path = pathlib.Path(path)
        if not zipfile.is_zipfile(self.path):
            raise PlanError(f"{self.path} is not a Canvas export (.imscc is a zip)")
        with zipfile.ZipFile(self.path) as zf:
            self.infos = zf.infolist()
            self.files = {i.filename: zf.read(i.filename) for i in self.infos}
        self.text = lambda name: self.files[name].decode("utf-8")
        self.assignments = {}
        for name in self.files:
            if name.endswith("/assignment_settings.xml"):
                xml = self.text(name)
                aid = re.search(r'<assignment identifier="([^"]+)"', xml).group(1)
                self.assignments[aid] = {"file": name, "title": tag(xml, "title"),
                                         "points": float(tag(xml, "points_possible") or 0), "rubric": tag(xml, "rubric_identifierref")}
        self.rubrics_xml = self.text("course_settings/rubrics.xml") if "course_settings/rubrics.xml" in self.files else None
        self.rubric_ids = set(re.findall(r'<rubric identifier="([^"]+)"', self.rubrics_xml or ""))
        lo = self.text("course_settings/learning_outcomes.xml") if "course_settings/learning_outcomes.xml" in self.files else ""
        self.outcomes = {}
        for m in re.finditer(r'<learningOutcome identifier="([^"]+)">(.*?)</learningOutcome>', lo, re.S):
            body = m.group(2)
            ratings = [(tag(r, "description"), float(tag(r, "points") or 0))
                       for r in re.findall(r"<rating>(.*?)</rating>", body, re.S)]
            self.outcomes[m.group(1)] = {"title": tag(body, "title"), "external": tag(body, "external_identifier"),
                                         "mastery": float(tag(body, "mastery_points") or 3.0),
                                         "ratings": ratings or DEFAULT_MASTERY}

    def outcome(self, ref):
        """Find an outcome by identifier, external identifier, or exact title."""
        if ref in self.outcomes:
            return ref, self.outcomes[ref]
        for oid, o in self.outcomes.items():
            if ref in (o["external"], o["title"]):
                return oid, o
        raise PlanError(f'outcome "{ref}" is not in the export (give its identifier, external identifier or exact title)')


def criterion_xml(cid, c):
    ratings = "".join(
        f"<rating><description>{esc(r['description'])}</description>"
        f"<long_description>{esc(r.get('long_description', ''))}</long_description>"
        f"<points>{float(r['points'])}</points><criterion_id>{cid}</criterion_id><id>{cid}_{i}</id></rating>"
        for i, r in enumerate(c["ratings"], 1))
    return (f"<criterion><criterion_id>{cid}</criterion_id><points>{float(c['points'])}</points>"
            f"<ignore_for_scoring>false</ignore_for_scoring><description>{esc(c['description'])}</description>"
            f"<long_description>{esc(c.get('long_description', ''))}</long_description><ratings>{ratings}</ratings></criterion>")


def outcome_criterion_xml(cid, oid, o):
    link = (f"<learning_outcome_external_identifier>{esc(o['external'])}</learning_outcome_external_identifier>"
            if o["external"] else f"<learning_outcome_identifierref>{oid}</learning_outcome_identifierref>")
    top = max(p for _, p in o["ratings"])
    ratings = "".join(f"<rating><description>{esc(d)}</description><points>{p}</points>"
                      f"<criterion_id>{cid}</criterion_id><id>{cid}_{i}</id></rating>" for i, (d, p) in enumerate(o["ratings"], 1))
    # ignore_for_scoring true: the criterion records mastery of the outcome without
    # changing the assignment's score, so the rubric total still equals its points.
    return (f"<criterion><criterion_id>{cid}</criterion_id><points>{top}</points><mastery_points>{o['mastery']}</mastery_points>"
            f"<ignore_for_scoring>true</ignore_for_scoring><description>{esc(o['title'])}</description>"
            f"<long_description></long_description>{link}<ratings>{ratings}</ratings></criterion>")


def plan_changes(export, plan):
    """Validate the plan against the export and return a list of (description, apply_fn)."""
    changes = []
    rubrics_xml = export.rubrics_xml or f'<?xml version="1.0" encoding="UTF-8"?>\n<rubrics {CANVAS_NS}>\n</rubrics>\n'
    new_rubrics, settings_edits = [], {}

    for n, r in enumerate(plan.get("create", []), 1):
        aid = r.get("assignment_id")
        a = export.assignments.get(aid)
        if not a:
            raise PlanError(f"create #{n}: assignment {aid!r} is not in the export")
        if a["rubric"] and not r.get("replace_existing"):
            raise PlanError(f'create #{n}: "{a["title"]}" already has a rubric; set "replace_existing": true to replace it')
        scored = sum(float(c["points"]) for c in r["criteria"])
        if abs(scored - a["points"]) > TOLERANCE:
            raise PlanError(f'create #{n}: "{a["title"]}" is worth {a["points"]:g} points but the criteria add up to {scored:g}')
        for c in r["criteria"]:
            pts = [float(x["points"]) for x in c["ratings"]]
            if not pts or max(pts) != float(c["points"]):
                raise PlanError(f'create #{n}: criterion "{c["description"]}" is worth {c["points"]} but its top rating is {max(pts) if pts else "missing"}')
        rid = ident("rubric", aid, r.get("title", ""))
        crit = "".join(criterion_xml(f"_{ident(rid, str(i))[1:9]}", c) for i, c in enumerate(r["criteria"]))
        for ref in r.get("outcomes", []):
            oid, o = export.outcome(ref)
            crit += outcome_criterion_xml(f"_{ident(rid, oid)[1:9]}", oid, o)
        title = r.get("title") or f'{a["title"]} rubric'
        new_rubrics.append(f'<rubric identifier="{rid}"><read_only>false</read_only><title>{esc(title)}</title>'
                           f"<reusable>false</reusable><public>false</public><points_possible>{a['points']}</points_possible>"
                           f"<hide_score_total>false</hide_score_total><free_form_criterion_comments>false</free_form_criterion_comments>"
                           f"<rating_order>descending</rating_order><criteria>{crit}</criteria></rubric>")
        settings_edits.setdefault(a["file"], {}).update({"rubric_identifierref": rid, "rubric_use_for_grading": "true",
                                                         "rubric_hide_points": "false", "rubric_hide_outcome_results": "false",
                                                         "rubric_hide_score_total": "false"})
        changes.append(f'create rubric "{title}" ({len(r["criteria"])} criteria, {scored:g} points'
                       f'{", " + str(len(r.get("outcomes", []))) + " outcome criteria" if r.get("outcomes") else ""}) and attach it to "{a["title"]}", used for grading')

    for n, add in enumerate(plan.get("add_outcomes", []), 1):
        rid = add.get("rubric_id")
        if rid not in export.rubric_ids:
            raise PlanError(f"add_outcomes #{n}: rubric {rid!r} is not in the export")
        oid, o = export.outcome(add["outcome"])
        rubric_block = re.search(rf'<rubric identifier="{re.escape(rid)}">.*?</rubric>', rubrics_xml, re.S).group(0)
        if (o["external"] and f">{o['external']}<" in rubric_block) or f">{oid}<" in rubric_block:
            raise PlanError(f'add_outcomes #{n}: the rubric already has a criterion for "{o["title"]}"')
        new_block = rubric_block.replace("</criteria>", outcome_criterion_xml(f"_{ident(rid, oid)[1:9]}", oid, o) + "</criteria>", 1)
        rubrics_xml = rubrics_xml.replace(rubric_block, new_block, 1)
        changes.append(f'add a criterion for outcome "{o["title"]}" to rubric {tag(rubric_block, "title")!r}, not counted toward the score')

    for n, rid in enumerate(plan.get("show_rating_levels", []), 1):
        if rid not in export.rubric_ids:
            raise PlanError(f"show_rating_levels #{n}: rubric {rid!r} is not in the export")
        block = re.search(rf'<rubric identifier="{re.escape(rid)}">.*?</rubric>', rubrics_xml, re.S).group(0)
        fixed = block.replace("<free_form_criterion_comments>true</free_form_criterion_comments>",
                              "<free_form_criterion_comments>false</free_form_criterion_comments>")
        if fixed == block:
            raise PlanError(f"show_rating_levels #{n}: rubric {tag(block, 'title')!r} already shows its rating levels")
        rubrics_xml = rubrics_xml.replace(block, fixed, 1)
        changes.append(f"show the rating levels of rubric {tag(block, 'title')!r} instead of a comment box")

    for n, aid in enumerate(plan.get("use_for_grading", []), 1):
        a = export.assignments.get(aid)
        if not a or not a["rubric"]:
            raise PlanError(f"use_for_grading #{n}: assignment {aid!r} is not in the export or has no rubric")
        settings_edits.setdefault(a["file"], {})["rubric_use_for_grading"] = "true"
        changes.append(f'use the rubric on "{a["title"]}" for grading, so a rating sets the score')

    if not changes:
        raise PlanError("the plan contains no changes")
    if new_rubrics:
        rubrics_xml = rubrics_xml.replace("</rubrics>", "".join(new_rubrics) + "\n</rubrics>", 1)
    return changes, rubrics_xml, settings_edits


def set_field(xml, name, value):
    if re.search(rf"<{name}>.*?</{name}>|<{name}/>", xml, re.S):
        return re.sub(rf"<{name}>.*?</{name}>|<{name}/>", f"<{name}>{value}</{name}>", xml, count=1, flags=re.S)
    return xml.replace("</assignment>", f"  <{name}>{value}</{name}>\n</assignment>", 1)


def write(export, rubrics_xml, settings_edits, out_path):
    files = dict(export.files)
    files["course_settings/rubrics.xml"] = rubrics_xml.encode("utf-8")
    for name, fields in settings_edits.items():
        xml = files[name].decode("utf-8")
        for k, v in fields.items():
            xml = set_field(xml, k, v)
        files[name] = xml.encode("utf-8")
    manifest = files["imsmanifest.xml"].decode("utf-8")
    if "course_settings/rubrics.xml" not in manifest and 'href="course_settings/course_settings.xml"' in manifest:
        manifest = manifest.replace('<file href="course_settings/course_settings.xml"/>',
                                    '<file href="course_settings/course_settings.xml"/>\n      <file href="course_settings/rubrics.xml"/>', 1)
        files["imsmanifest.xml"] = manifest.encode("utf-8")
    # Every entry keeps the original's timestamp (new entries get a fixed one), so the same
    # export and plan always produce the same bytes and a rebuild changes nothing.
    infos = {i.filename: i for i in export.infos}
    order = [i.filename for i in export.infos] + sorted(n for n in files if n not in infos)
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in order:
            info = zipfile.ZipInfo(name, infos[name].date_time if name in infos else (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = infos[name].external_attr if name in infos else 0o644 << 16
            zf.writestr(info, files[name])


def main(argv=None):
    ap = argparse.ArgumentParser(description="Write reviewed rubrics and outcome links into a copy of a Canvas export")
    ap.add_argument("export", help="the original .imscc (never modified)")
    ap.add_argument("plan", help="rubric_plan.json")
    ap.add_argument("--apply", action="store_true", help="write the new export (default: dry run)")
    ap.add_argument("--out", help="where to write it (default: COURSE.rubrics.imscc beside the original)")
    args = ap.parse_args(argv)
    try:
        export = Export(args.export)
        plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))
        changes, rubrics_xml, edits = plan_changes(export, plan)
    except (PlanError, OSError, json.JSONDecodeError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(("Applying" if args.apply else "Dry run. Run again with --apply to make") + f" {len(changes)} change(s):")
    for i, c in enumerate(changes, 1):
        print(f"  {i}. {c}")
    if args.apply:
        src = pathlib.Path(args.export)
        out = pathlib.Path(args.out) if args.out else src.with_name(src.stem + ".rubrics.imscc")
        if out.resolve() == src.resolve():
            print("error: the output would overwrite the original export", file=sys.stderr)
            return 2
        write(export, rubrics_xml, edits, out)
        print(f"Wrote {out}. The original export was not changed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
