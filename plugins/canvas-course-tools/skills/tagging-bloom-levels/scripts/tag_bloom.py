#!/usr/bin/env python3
"""Propose a Bloom's level for every lecture, lab, activity, assignment, quiz and
discussion in a Canvas course, and check that each learning outcome climbs.

Usage:
    python3 tag_bloom.py course_model.json [--out-dir DIR] [--levels bloom_levels.csv]
    python3 tag_bloom.py COURSE.imscc        [--out-dir DIR]

Reads the course_model.json written by the reading-canvas-exports skill (or runs it on an
.imscc). Writes:

    bloom_levels.csv     one row per item: proposed level, confidence, evidence, and an
                         empty confirmed_level column for the instructor
    bloom_levels.json    the same, plus every outcome's sequence of levels
    bloom_report.md      assumptions, the levels by week, each outcome's progression,
                         and the items that need a person to decide

A PROPOSED LEVEL IS NOT A TAUGHT LEVEL. Every level this script writes is a proposal read
from the verbs the course uses on students. Pass the CSV back with --levels after the
instructor fills in confirmed_level, and the confirmed values are used instead.

Verb table: assets/bloom_verbs.json. Standard library only. Python 3.10 or later.
"""
import argparse
import csv
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
VERBS = HERE.parent / "assets" / "bloom_verbs.json"
READER = HERE.parent.parent / "reading-canvas-exports" / "scripts" / "read_export.py"
NAMES = {}
# Lines that introduce learning objectives. What follows them is the strongest evidence
# of the level a session or assignment asks for.
OBJECTIVE_CUE = re.compile(r"\bobjectives?\b|\bwill be able to\b|\bafter this\b.*\byou can\b|\bby the end of\b"
                           r"|\blearning outcomes?\b|\bgoals?\b|\byou will learn\b|\bstudents will\b", re.I)
OBJECTIVE_WINDOW = 12  # lines after a cue that are read as objectives
LEADING = re.compile(r"^(?:[-*•\d.)\s]+)?(?:(?:students|you)\s+(?:will|can|should)\s+(?:be\s+able\s+to\s+)?)?", re.I)
TYPES = [("lab", re.compile(r"\b(lab|labs|studio|workshop)\b", re.I)),
         ("activity", re.compile(r"\b(activity|exercise|drill|in-class|practice)\b", re.I)),
         ("lecture", re.compile(r"\b(lecture|session|class \d|week \d+ lecture|module \d+ lecture)\b", re.I))]
CONF_ORDER = {"high": 0, "medium": 1, "low": 2, "none": 3}
# Items graded from a roll the instructor keeps. They record presence, not a learning task,
# so no level is proposed for them.
ATTENDANCE = re.compile(r"\b(attendance|roll\s*call|check[- ]?in)\b", re.I)


def load_verbs():
    data = json.loads(VERBS.read_text(encoding="utf-8"))
    table = []
    for lvl in data["levels"]:
        NAMES[lvl["level"]] = lvl["name"]
        for v in lvl["verbs"]:
            # The bare verb only. An objective or instruction opens with it ("Name the
            # data", "Explain why"); "Named reviewer personas" is a heading, and accepting
            # inflected forms let it pull five assignments down to Remember.
            pattern = r"\b" + r"\s+".join(map(re.escape, v.split())) + r"\b(?!-)"
            table.append((lvl["level"], v, re.compile(pattern, re.I)))
    table.sort(key=lambda t: -t[0])
    return table, data.get("excluded", {})


def leading_verb(line, table):
    """The level of the verb a line opens with, after 'Students will be able to' and list marks."""
    body = LEADING.sub("", line.split("\t")[0].strip(), count=1)
    first = body[:40]
    for level, verb, rx in table:
        m = rx.match(first)
        if m:
            return level, verb
    return None


class Tagger:
    def __init__(self, model, confirmed=None):
        self.m = model
        self.table, self.excluded = load_verbs()
        self.confirmed = confirmed or {}
        self.module_of = {}
        for mod in model["modules"]:
            for it in mod["items"]:
                if it.get("ref"):
                    self.module_of.setdefault(it["ref"], mod)
        first = model["inferred"].get("first_day")
        self.first_day = dt.date.fromisoformat(first) if first else None
        self.rows = []
        self.findings = []

    def week(self, item):
        mod = self.module_of.get(item["id"])
        m = re.search(r"\bweek\s*0*(\d{1,2})\b", (mod or {}).get("title") or "", re.I)
        if m:
            return int(m.group(1))
        if item.get("due_local") and self.first_day:
            d = dt.datetime.fromisoformat(item["due_local"]).date()
            return (d - (self.first_day - dt.timedelta(days=self.first_day.weekday()))).days // 7 + 1
        return None

    def kind(self, item):
        if item.get("kind") != "page":
            return item.get("kind")
        if item.get("front_page"):
            return "page"
        for name, rx in TYPES:
            if rx.search(item.get("title") or ""):
                return name
        # A page filed in a module named by week is a class session, whatever its title.
        mod = self.module_of.get(item["id"])
        if mod and re.search(r"\bweek\s*\d", mod.get("title") or "", re.I):
            return "session"
        return "page"

    def propose(self, item):
        if ATTENDANCE.search(item.get("title") or ""):
            return None, "not applicable", "graded from attendance; records presence, not a learning task", 0
        lines = (item.get("text") or "").splitlines()
        objective, instruction = [], []
        cue_until = -1
        for i, line in enumerate(lines):
            if OBJECTIVE_CUE.search(line) and len(line) < 160:
                cue_until = i + OBJECTIVE_WINDOW
                continue
            hit = leading_verb(line, self.table)
            if not hit:
                continue
            (objective if i <= cue_until else instruction).append((hit[0], hit[1], line.split("\t")[0][:160]))
        title_hit = leading_verb(item.get("title") or "", self.table)
        for tier, conf in ((objective, "high"), (instruction, "medium")):
            if tier:
                top = max(t[0] for t in tier)
                ev = [t for t in tier if t[0] == top][:3]
                return top, conf, "; ".join(f'"{e[1]}" in "{e[2]}"' for e in ev), len(tier)
        if title_hit:
            return title_hit[0], "low", f'"{title_hit[1]}" in the title only', 1
        return None, "none", "no line opens with a verb from the table", 0

    def outcomes_of(self, item):
        by_id = {o["id"]: o for o in self.m["outcomes"]}
        by_ext = {o["external_identifier"]: o for o in self.m["outcomes"] if o.get("external_identifier")}
        found = {}
        rubric = next((r for r in self.m["rubrics"] if r["id"] == item.get("rubric")), None)
        for c in (rubric or {}).get("criteria", []):
            o = by_id.get(c.get("outcome")) or by_ext.get(c.get("outcome_external_id"))
            if o:
                found[o["id"]] = o
        for o in self.m["outcomes"]:
            for a in o.get("alignments", []):
                if a.get("content_id") in (item["id"], item.get("rubric")):
                    found[o["id"]] = o
        return list(found.values())

    def run(self):
        items = self.m["pages"] + self.m["assignments"] + self.m["quizzes"] + self.m["discussions"]
        for x in items:
            if (x.get("workflow_state") or "") not in ("active", "published") and x.get("kind") == "page" \
                    and x["id"] not in self.module_of:
                continue  # an unpublished page in no module is not course content students meet
            level, conf, evidence, n = self.propose(x)
            row = {"id": x["id"], "title": x["title"], "type": self.kind(x), "week": self.week(x),
                   "due": (x.get("due_local") or "")[:10], "proposed_level": NAMES.get(level, ""),
                   "proposed_level_number": level, "confidence": conf, "evidence": evidence,
                   "outcomes": "; ".join(o["title"] for o in self.outcomes_of(x)),
                   "_outcome_ids": [o["id"] for o in self.outcomes_of(x)],
                   "confirmed_level": self.confirmed.get(x["id"], {}).get("confirmed_level", ""),
                   "note": self.confirmed.get(x["id"], {}).get("note", "")}
            self.rows.append(row)
        self.rows.sort(key=lambda r: (r["week"] is None, r["week"] or 0, r["due"] or "9", r["title"]))
        self.check()
        return self

    def level_of(self, row):
        """The confirmed level if the instructor gave one, else the proposal."""
        if row["confirmed_level"]:
            for n, name in NAMES.items():
                if name.lower() == row["confirmed_level"].strip().lower():
                    return n, "confirmed"
        return row["proposed_level_number"], "proposed"

    def check(self):
        for r in self.rows:
            if r["type"] == "page" or r["confidence"] == "not applicable":
                continue  # general pages and attendance are not expected to carry a level
            if r["proposed_level_number"] is None and not r["confirmed_level"]:
                self.findings.append(("warning", "No level found", r["title"],
                                      "no verb from the table opens any line; a person must read it and decide"))
            elif r["confidence"] == "low" and not r["confirmed_level"]:
                self.findings.append(("info", "Weak evidence", r["title"], f"level from the title only ({r['evidence']})"))
        self.progressions = []
        for o in self.m["outcomes"]:
            assessed = [r for r in self.rows if o["id"] in r["_outcome_ids"] and r["type"] in ("assignment", "quiz", "discussion")]
            assessed.sort(key=lambda r: r["due"] or "9")
            seq = [(r["title"], *self.level_of(r)) for r in assessed]
            known = [s for s in seq if s[1] is not None]
            entry = {"outcome": o["title"], "level": o.get("level"), "items": [
                {"title": t, "level": NAMES.get(n), "source": src} for t, n, src in seq]}
            if not assessed:
                status = "not measured by any assignment, quiz or discussion"
                self.findings.append(("warning", "Outcome not measured", o["title"], status))
            elif len(known) < 2:
                status = "measured by one item with a known level, so there is no progression to judge"
                self.findings.append(("info", "Outcome measured once", o["title"], status))
            else:
                levels = [k[1] for k in known]
                if len(set(levels)) == 1:
                    status = f"does not climb: every item is {NAMES[levels[0]]}"
                    self.findings.append(("warning", "Outcome does not climb", o["title"], status))
                elif levels[-1] < levels[0]:
                    status = f"ends at {NAMES[levels[-1]]}, below where it starts ({NAMES[levels[0]]})"
                    self.findings.append(("warning", "Outcome ends lower than it starts", o["title"], status))
                else:
                    status = f"climbs from {NAMES[levels[0]]} to {NAMES[max(levels)]}"
            entry["status"] = status
            self.progressions.append(entry)


def write_csv(rows, path):
    cols = ["id", "title", "type", "week", "due", "proposed_level", "confidence", "evidence", "outcomes",
            "confirmed_level", "note"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


def read_confirmed(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return {r["id"]: r for r in csv.DictReader(fh) if r.get("id")}


def report(model, t):
    sev = {k: sum(f[0] == k for f in t.findings) for k in ("warning", "info")}
    known = [r for r in t.rows if r["proposed_level_number"]]
    confirmed = sum(1 for r in t.rows if r["confirmed_level"])
    out = [f"# Bloom's levels: {model['course']['title'] or model['source']['file']}", "",
           f"{len(t.rows)} items. A level was proposed for {len(known)}. Confirmed by the instructor: {confirmed}. "
           f"{sev['warning']} warnings, {sev['info']} notes.", "",
           "**Every level below is a proposal** read from the verbs the course uses on students, unless the "
           "Confirmed column says otherwise. Confirm them in `bloom_levels.csv` (the `confirmed_level` column) "
           "and run again with `--levels bloom_levels.csv`.", "",
           "## How levels were proposed", "",
           "- **High confidence:** a verb opens a line in a learning-objectives section.",
           "- **Medium confidence:** a verb opens an instruction line elsewhere in the item.",
           "- **Low confidence:** a verb opens the title, and nothing else was found.",
           "- **Unknown:** no line opens with a verb from the table. Nothing is guessed.",
           "- When several verbs appear, the highest level wins: work that analyzes in order to judge is judging.",
           f"- Verbs excluded because published lists disagree on their level: {', '.join(sorted(t.excluded))}.", "",
           "## Levels by week", "", "| Week | " + " | ".join(NAMES[n] for n in sorted(NAMES)) + " | Unknown |",
           "|---|" + "---|" * (len(NAMES) + 1)]
    weeks = sorted({r["week"] for r in t.rows if r["week"] is not None})
    for w in weeks:
        rows = [r for r in t.rows if r["week"] == w]
        counts = [sum(1 for r in rows if t.level_of(r)[0] == n) for n in sorted(NAMES)]
        unknown = sum(1 for r in rows if t.level_of(r)[0] is None)
        out.append(f"| {w} | " + " | ".join(str(c or "") for c in counts) + f" | {unknown or ''} |")
    out += ["", "## Outcome progression", "",
            "Each outcome's assessed items in due-date order. An outcome should reach more than one level and end at or "
            "above where it starts. Dips along the way are normal: applying a technique is often how students get the "
            "material the next analysis needs.", ""]
    for p in t.progressions:
        steps = " → ".join(f"{i['title']} ({i['level'] or 'unknown'}{', confirmed' if i['source'] == 'confirmed' else ''})"
                           for i in p["items"]) or "no assessed items"
        out.append(f"- **{p['outcome']}** ({p['level']} level): {p['status']}. {steps}")
    out += ["", "## Findings", ""]
    order = {"warning": 0, "info": 1}
    for i, f in enumerate(sorted(t.findings, key=lambda f: (order[f[0]], f[1], f[2])), 1):
        out.append(f"{i}. **{f[0].capitalize()}: {f[1]}.** {f[2]}: {f[3]}.")
    if not t.findings:
        out.append("No findings.")
    out += ["", "## Every item", "", "| Week | Item | Type | Proposed | Confidence | Confirmed | Evidence |",
            "|---|---|---|---|---|---|---|"]
    for r in t.rows:
        out.append(f"| {r['week'] or '—'} | {r['title']} | {r['type']} | {r['proposed_level'] or 'unknown'} | "
                   f"{r['confidence']} | {r['confirmed_level'] or '—'} | {r['evidence'].replace('|', '/')} |")
    out += ["", "## What this does not check", "",
            "- Whether students actually work at the level a verb names. A verb is evidence of intent, not of what happened in the room.",
            "- Objectives written as images, attached files, or in words this table does not list.",
            "- Pages that are unpublished and in no module.", ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Propose Bloom's levels and check outcome progression")
    ap.add_argument("input", help="course_model.json, or a .imscc export")
    ap.add_argument("--out-dir", help="where to write the outputs (default: beside the input)")
    ap.add_argument("--levels", help="a bloom_levels.csv with confirmed_level filled in")
    args = ap.parse_args(argv)
    src = pathlib.Path(args.input)
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else src.resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".imscc":
        if not READER.exists():
            print("error: given an .imscc, but the reading-canvas-exports skill is not installed beside this one.",
                  file=sys.stderr)
            return 2
        model_path = out_dir / "course_model.json"
        done = subprocess.run([sys.executable, str(READER), str(src), "--out", str(model_path)])
        if done.returncode:
            return done.returncode
        src = model_path
    try:
        model = json.loads(src.read_text(encoding="utf-8"))
        confirmed = read_confirmed(args.levels) if args.levels else {}
    except (OSError, json.JSONDecodeError, csv.Error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    t = Tagger(model, confirmed).run()
    write_csv(t.rows, out_dir / "bloom_levels.csv")
    (out_dir / "bloom_levels.json").write_text(json.dumps(
        {"items": [{k: v for k, v in r.items() if not k.startswith("_")} for r in t.rows],
         "progressions": t.progressions,
         "findings": [dict(zip(("severity", "check", "subject", "message"), f)) for f in t.findings]},
        indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "bloom_report.md").write_text(report(model, t), encoding="utf-8")
    known = sum(1 for r in t.rows if r["proposed_level_number"])
    print(f"{len(t.rows)} items; level proposed for {known}; "
          f"{sum(1 for r in t.rows if r['confirmed_level'])} confirmed; "
          f"{sum(f[0] == 'warning' for f in t.findings)} warnings")
    for p in t.progressions:
        print(f"  {p['outcome']}: {p['status']}")
    print(f"Wrote {out_dir / 'bloom_report.md'}, bloom_levels.csv and bloom_levels.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
