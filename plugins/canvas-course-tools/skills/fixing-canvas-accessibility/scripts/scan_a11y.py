#!/usr/bin/env python3
"""Scan every HTML page in a Canvas export for accessibility problems and write a fix plan.

Usage:
    python3 scan_a11y.py COURSE.imscc [--out-dir DIR]

Writes:
    a11y_report.md     findings by page, what was fixed automatically in the plan, and
                       what this scan does not check
    a11y_plan.json     every fixable finding: "auto" fixes have one right answer,
                       "proposed" ones are prefilled for review, "needs_value" ones are
                       empty until a person (or Claude, for the person to review) fills them
Then run fix_a11y.py with the plan. The export is never modified.

Rules and their WCAG 2.1 success criteria: references/rules.md. Standard library only.
"""
import argparse
import hashlib
import html
import json
import pathlib
import re
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import a11y_html as A  # noqa: E402

STATUS_BY_FIX = {"rename": "auto", "remove": "auto", "set_style:color": "auto", "set_attr:scope": "auto",
                 "header_row": "proposed", "caption": "proposed", "set_attr:title": "proposed",
                 "set_attr:alt": "needs_value", "link_text": "needs_value"}
NOT_CHECKED = {".pdf": "PDF", ".doc": "Word", ".docx": "Word", ".ppt": "PowerPoint", ".pptx": "PowerPoint",
               ".xls": "Excel", ".xlsx": "Excel", ".mp4": "video", ".mov": "video", ".mp3": "audio", ".m4a": "audio"}


def sources(zf):
    """(path, title, html) for every HTML body this scan can check and fix."""
    names = zf.namelist()
    titles = {}
    for n in names:
        if n.endswith("/assignment_settings.xml"):
            xml = zf.read(n).decode("utf-8", "replace")
            m = re.search(r"<title>(.*?)</title>", xml, re.S)
            titles[n.split("/")[0]] = html.unescape(m.group(1)) if m else n
    for n in sorted(names):
        if not n.lower().endswith((".html", ".htm")):
            continue
        raw = zf.read(n).decode("utf-8", "replace")
        if n == "course_settings/syllabus.html":
            title = "Syllabus"
        elif n.startswith("wiki_content/"):
            m = re.search(r"<title>(.*?)</title>", raw, re.S)
            title = html.unescape(m.group(1).strip()) if m else n
        elif n.split("/")[0] in titles:
            title = titles[n.split("/")[0]]
        else:
            title = n.split("/")[-1]
        yield n, title, raw


def main(argv=None):
    ap = argparse.ArgumentParser(description="Scan a Canvas export for accessibility problems")
    ap.add_argument("export", help="the .imscc file")
    ap.add_argument("--out-dir", help="where to write the report and plan (default: beside the export)")
    args = ap.parse_args(argv)
    src = pathlib.Path(args.export)
    if not zipfile.is_zipfile(src):
        print(f"error: {src} is not a Canvas export (.imscc is a zip)", file=sys.stderr)
        return 2
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else src.resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    findings, pages = [], 0
    with zipfile.ZipFile(src) as zf:
        for name, title, raw in sources(zf):
            pages += 1
            findings += A.check(name, raw, title)
        others = {}
        for n in zf.namelist():
            kind = NOT_CHECKED.get(pathlib.PurePosixPath(n.lower()).suffix)
            if kind:
                others[kind] = others.get(kind, 0) + 1
        topics = sum(1 for n in zf.namelist() if re.fullmatch(r"[^/]+\.xml", n) and b"<topic" in zf.read(n)[:400])
        quizzes = sum(1 for n in zf.namelist() if n.endswith("assessment_meta.xml"))
    for i, f in enumerate(findings, 1):
        f["id"] = f"X{i}"
        f["status"] = STATUS_BY_FIX.get(f["fix"]) if f["fix"] else None
        if f["status"] == "needs_value":
            f["value"] = None
    plan = {"export": src.name, "sha256": hashlib.sha256(src.read_bytes()).hexdigest(),
            "how_to_use": "Fill every value that is null (alt text, link text), review the 'proposed' ones, set any value to "
                          "\"skip\" to leave that element alone, then run fix_a11y.py.",
            "fixes": [{k: f[k] for k in ("id", "rule", "status", "file", "title", "element", "fix", "value", "needs", "message")}
                      for f in findings if f["fix"]]}
    (out_dir / "a11y_plan.json").write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    rules = {}
    for f in findings:
        rules.setdefault(f["rule"], []).append(f)
    count = lambda st: sum(1 for f in plan["fixes"] if f["status"] == st)
    out = [f"# Accessibility scan: {src.name}", "",
           f"{pages} HTML pages checked. {len(findings)} findings: {sum(f['severity'] == 'defect' for f in findings)} defects, "
           f"{sum(f['severity'] == 'warning' for f in findings)} warnings.", "",
           f"The fix plan has {count('auto')} automatic fixes, {count('proposed')} proposed fixes to review, and "
           f"{count('needs_value')} that need a person to write text (alt text and link text).", "",
           "## By rule", "", "| Rule | WCAG | Count | Fix |", "|---|---|---|---|"]
    for rule in sorted(rules, key=lambda r: -len(rules[r])):
        f0 = rules[rule][0]
        out.append(f"| {rule} | {f0['wcag']} | {len(rules[rule])} | {STATUS_BY_FIX.get(f0['fix'], 'report only') if f0['fix'] else 'report only'} |")
    out += ["", "## By page", ""]
    by_page = {}
    for f in findings:
        by_page.setdefault((f["title"], f["file"]), []).append(f)
    for (title, file), fs in sorted(by_page.items(), key=lambda kv: (-len(kv[1]), kv[0][0])):
        out.append(f"### {title} ({len(fs)})")
        out.append("")
        out += [f"- **{f['id']} {f['rule']}** ({f['severity']}): {f['message']}." for f in fs]
        out.append("")
    if not findings:
        out.append("No findings.")
    out += ["## Not checked", "",
            "These are in the export but outside what this scan reads. Check them another way:", ""]
    for kind, n in sorted(others.items()):
        out.append(f"- {n} {kind} file(s): open each in its own accessibility checker (for example Acrobat, or Word's Check Accessibility).")
    out += [f"- {topics} discussion(s) and {quizzes} quiz description(s): their text is stored inside XML in the export; use the Canvas editor's accessibility checker on them.",
            "- Whether alt text is accurate, whether a heading's words describe its section, and whether video has captions: these need a person.",
            "- Contrast set by stylesheets or themes rather than inline styles.", ""]
    (out_dir / "a11y_report.md").write_text("\n".join(out), encoding="utf-8")
    print(f"{pages} pages, {len(findings)} findings; plan: {count('auto')} auto, {count('proposed')} proposed, "
          f"{count('needs_value')} need text")
    print(f"Wrote {out_dir / 'a11y_report.md'} and a11y_plan.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
