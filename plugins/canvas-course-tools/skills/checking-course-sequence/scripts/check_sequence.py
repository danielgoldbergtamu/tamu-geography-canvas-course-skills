#!/usr/bin/env python3
"""Check a Canvas course's sequence and build its graph.

Usage:
    python3 check_sequence.py course_model.json [--out-dir DIR] [--fail-on defect|warning]
    python3 check_sequence.py COURSE.imscc        [--out-dir DIR]

Reads the course_model.json written by the reading-canvas-exports skill. Given an
.imscc instead, it runs that skill's reader first, if the reader is installed beside
this skill. Writes three files to --out-dir (default: the model's folder):

    sequence_report.md       what a person reads: assumptions, timeline, findings
    sequence_findings.json   the same findings, for other tools
    course_graph.json        nodes and edges: weeks, meetings, modules, items, links

The checks and what each does NOT check are in references/checks.md.
Standard library only. Python 3.10 or later.
"""
import argparse
import datetime as dt
import json
import pathlib
import re
import subprocess
import sys
import urllib.parse

HERE = pathlib.Path(__file__).resolve().parent
READER = HERE.parent.parent / "reading-canvas-exports" / "scripts" / "read_export.py"
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
DAY_WORDS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_RE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b"
                     r"|\b(\d{1,2})/(\d{1,2})(?:/(\d{2,4}))?\b", re.I)
# Words that make a submission type a real submission. "none" and "not_graded" are not.
NO_SUBMISSION = {"none", "not_graded", ""}
# A draft and its final, from Anthropic-independent course practice: GEOG 476 found that
# seven days left four to grade and three to revise; fourteen gave room for both.
REVISION_GAP_DAYS = 14
SEVERITY_ORDER = {"defect": 0, "warning": 1, "info": 2}
# Items graded from a roll the instructor keeps, not from anything a student submits.
ATTENDANCE = re.compile(r"\b(attendance|roll\s*call|check[- ]?in|present)\b", re.I)
# How far ahead an unpublished deadline is treated as urgent. GEOG 476 set seven days
# between a week opening and its first deadline (rule R140 there).
LEAD_DAYS = 7
SYLLABUS = {"title": "Syllabus tab", "id": "syllabus", "_kind": "syllabus"}


# ---------------------------------------------------------------- helpers

def norm(text):
    """Lowercase ASCII letters and digits only, single-spaced. Survives damaged dashes."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", (text or "").lower()).split())


def local_date(item):
    value = item.get("due_local")
    return dt.datetime.fromisoformat(value).date() if value else None


def dates_in(text, year):
    out = []
    for m in DATE_RE.finditer(text or ""):
        try:
            if m.group(1):
                out.append(dt.date(year, MONTHS[m.group(1).lower()[:3]], int(m.group(2))))
            else:
                y = int(m.group(5)) if m.group(5) else year
                y = y + 2000 if y < 100 else y
                out.append(dt.date(y, int(m.group(3)), int(m.group(4))))
        except (ValueError, KeyError):
            continue
    return out


def human(d):
    return f"{DAYS[d.weekday()]} {d.day} {d.strftime('%b')} {d.year}" if d else "no date"


def title_pattern(title):
    words = norm(title).split()
    if not words:
        return None
    # A trailing number must not match a longer number: "Engagement 1" is not "Engagement 10".
    return re.compile(r"(?<![a-z0-9])" + r"\s+".join(map(re.escape, words)) + r"(?![a-z0-9])")


class Checker:
    def __init__(self, model, as_of=None):
        self.m = model
        self.as_of = as_of or self.read_date(model)
        self.findings = []
        self.status = {}
        inf = model["inferred"]
        self.tz_known = inf["time_zone"]["value"] is not None
        self.sessions = model["sessions"]
        self.first_day = dt.date.fromisoformat(inf["first_day"]) if inf.get("first_day") else None
        self.items = [dict(x, _kind=x.get("kind", "page")) for x in
                      model["pages"] + model["assignments"] + model["quizzes"] + model["discussions"]]
        self.by_id = {x["id"]: x for x in self.items}
        self.page_by_slug = {p["slug"]: p for p in model["pages"] if p.get("slug")}
        self.dated = [x for x in model["assignments"] + model["quizzes"] if x.get("due_local")]
        self.module_of = {}
        for mod in model["modules"]:
            for it in mod["items"]:
                if it.get("ref"):
                    self.module_of.setdefault(it["ref"], mod)
        self.year = (self.first_day or dt.date.today()).year
        self.patterns = [(x, title_pattern(x["title"])) for x in self.dated if len(norm(x["title"])) >= 5]

    @staticmethod
    def read_date(model):
        """The local date in the course's time zone when the export was read.

        read_at is UTC. In the evening in the Americas the UTC date is already
        tomorrow, so taking its date counted deadlines from the wrong day.
        """
        read = (model.get("source") or {}).get("read_at")
        if not read:
            return dt.date.today()
        when = dt.datetime.fromisoformat(read)
        tz_name = model["inferred"]["time_zone"].get("value")
        try:
            from zoneinfo import ZoneInfo
            return when.astimezone(ZoneInfo(tz_name)).date() if tz_name else when.date()
        except Exception:
            # No time-zone database (Windows without tzdata): use the offset of the
            # nearest dated item, which the reader already converted correctly.
            offsets = [dt.datetime.fromisoformat(x["due_local"]).utcoffset() for x in
                       model["assignments"] + model["quizzes"] if x.get("due_local")]
            return (when + offsets[0]).date() if offsets else when.date()

    # ------------------------------------------------------------ weeks
    def week_of(self, day):
        if not self.first_day or not day:
            return None
        start = self.first_day - dt.timedelta(days=self.first_day.weekday())
        return (day - start).days // 7 + 1

    def module_week(self, mod):
        if not mod:
            return None
        m = re.search(r"\bweek\s*0*(\d{1,2})\b", mod.get("title") or "", re.I)
        return int(m.group(1)) if m else None

    def first_meeting_in_week(self, week):
        for s in self.sessions:
            if s["week"] == week and not s["cancelled"]:
                return dt.date.fromisoformat(s["date"])
        return None

    def add(self, check, severity, item, message, evidence):
        self.findings.append({"check": check, "severity": severity,
                              "item": item.get("title") if item else None,
                              "kind": (item.get("_kind") or item.get("kind")) if item else None,
                              "item_id": item.get("id") if item else None,
                              "message": message, "evidence": evidence})

    def not_run(self, check, why):
        self.status[check] = f"not run: {why}"

    # ------------------------------------------------------------ checks
    def c1_date_drift(self):
        """A date written in course text disagrees with the item's due date."""
        name = "1 Date drift"
        if not self.tz_known:
            return self.not_run(name, "the course time zone could not be inferred, so local due dates are unknown")
        count = 0
        # Tables in the syllabus: a Due column holding an item title.
        for table in self.m["syllabus"].get("tables", []):
            header = table[0]
            due_cols = {i: c for i, c in enumerate(header) if re.search(r"\bdue\b", c, re.I)}
            if not due_cols:
                continue
            for row in table[1:]:
                anchors = [d for c in row for d in dates_in(c, self.year)]
                for i, head in due_cols.items():
                    if i >= len(row):
                        continue
                    cell = norm(row[i])
                    for item, pat in self.patterns:
                        if not pat or not pat.search(cell):
                            continue
                        actual = local_date(item)
                        explicit = dates_in(row[i], self.year)
                        wd = next((DAY_WORDS[w[:3]] for w in re.findall(r"[a-z]+", head.lower()) if w[:3] in DAY_WORDS), None)
                        if explicit:
                            promised = explicit[0]
                        elif wd is not None and anchors:
                            week_start = anchors[0] - dt.timedelta(days=anchors[0].weekday())
                            promised = week_start + dt.timedelta(days=wd)
                        else:
                            continue
                        count += 1
                        if promised != actual:
                            self.add(name, "defect", item,
                                     f"the syllabus schedule says {human(promised)}; Canvas has it due {human(actual)}",
                                     f'syllabus table row "{" | ".join(row)[:180]}"')
        # Sentences anywhere in course text that name an item, say "due", and give a date.
        sources = [("syllabus", None, self.m["syllabus"]["text"])] + [
            (x.get("kind", "page"), x, x.get("text") or "") for x in self.items]
        for kind, owner, text in sources:
            for sentence in re.split(r"(?<=[.!?])\s+|\n", text):
                low = norm(sentence)
                if " due" not in " " + low:
                    continue
                written = dates_in(sentence, self.year)
                if not written:
                    continue
                for item, pat in self.patterns:
                    if not pat or not pat.search(low):
                        continue
                    if owner is not None and owner is not item and len(self.patterns) and \
                            sum(1 for _, p in self.patterns if p and p.search(low)) > 1:
                        continue  # a sentence naming several items cannot say which date is whose
                    actual = local_date(item)
                    count += 1
                    if actual not in written:
                        where = "the Syllabus tab" if owner is None else f'{kind} "{owner["title"]}"'
                        self.add(name, "defect", item,
                                 f"{where} gives {', '.join(human(d) for d in written)}; Canvas has it due {human(actual)}",
                                 f'"{sentence.strip()[:200]}"')
        self.status[name] = f"run: {count} written due dates compared"

    def c2_dead_links(self):
        name = "2 Dead links"
        files = {urllib.parse.unquote(f).lower() for f in self.m.get("files", [])}
        sources = [("syllabus", SYLLABUS, self.m["syllabus"].get("links", []))] + [
            (x["_kind"], x, x.get("links", [])) for x in self.items]
        checked = 0
        for kind, owner, links in sources:
            for link in links:
                target = (link.get("target") or "").split("#")[0]
                if link["kind"] == "page":
                    checked += 1
                    if target not in self.by_id and target not in self.page_by_slug:
                        self.add(name, "defect", owner, f'links to a page that is not in the course ("{link.get("text") or target}")',
                                 link["href"])
                elif link["kind"] in ("assignment", "quiz", "discussion"):
                    checked += 1
                    if target not in self.by_id:
                        self.add(name, "defect", owner, f'links to a {link["kind"]} that is not in the course ("{link.get("text") or target}")',
                                 link["href"])
                elif link["kind"] == "file":
                    path = urllib.parse.unquote(target).lower()
                    if path.endswith("/"):
                        continue  # a folder link, which Canvas resolves to the folder
                    checked += 1
                    if path not in files:
                        self.add(name, "defect", owner, f'{"shows an image" if link.get("tag") == "img" else "links to a file"} that is not in the export',
                                 link["href"])
        self.status[name] = f"run: {checked} internal links resolved"

    def c3_due_before_taught(self):
        name = "3 Due before taught"
        if not self.sessions:
            return self.not_run(name, "the class meeting pattern could not be inferred")
        weekly = [m for m in self.m["modules"] if self.module_week(m)]
        if not weekly:
            return self.not_run(name, "no module is named by week (for example 'Week 3'), so the week each item is taught in is unknown")
        checked = 0
        for item in self.dated:
            mod = self.module_of.get(item["id"])
            week = self.module_week(mod)
            if not week:
                continue
            teach = self.first_meeting_in_week(week)
            due = local_date(item)
            if not teach or not due:
                continue
            checked += 1
            if due < teach:
                self.add(name, "defect", item,
                         f"due {human(due)}, before the first class of week {week} ({human(teach)}), the week its module covers",
                         f'module "{mod["title"]}"')
        self.status[name] = f"run: {checked} dated items placed in week modules"

    def c4_nothing_to_grade(self):
        name = "4 Graded with nothing to grade"
        checked = 0
        for a in self.m["assignments"]:
            if not a.get("points_possible") or a.get("omit_from_final_grade"):
                continue
            checked += 1
            subs = set(a.get("submission_types") or [])
            if subs <= NO_SUBMISSION and not a.get("rubric") and ATTENDANCE.search(a.get("title") or ""):
                self.add(name, "info", a,
                         f'worth {a["points_possible"]:g} points with nothing to submit and no rubric; the title suggests it is graded from attendance records, so confirm that is intended',
                         f"submission types: {', '.join(sorted(subs)) or 'none'}")
            elif subs <= NO_SUBMISSION and not a.get("rubric"):
                self.add(name, "defect", a,
                         f'worth {a["points_possible"]:g} points with nothing to submit and no rubric, so neither the student nor the grader can see what earns the points',
                         f"submission types: {', '.join(sorted(subs)) or 'none'}")
        self.status[name] = f"run: {checked} graded assignments"

    def c5_not_in_module(self):
        name = "5 Not in any module"
        linked = {l.get("target", "").split("#")[0] for x in self.items for l in x.get("links", [])}
        linked |= {l.get("target", "").split("#")[0] for l in self.m["syllabus"].get("links", [])}
        checked = 0
        for x in self.items:
            if (x.get("workflow_state") or "") not in ("active", "published"):
                continue
            if x.get("front_page"):
                continue
            if ATTENDANCE.search(x.get("title") or "") and x["_kind"] == "assignment":
                continue  # graded from the roll; students have nothing to open
            checked += 1
            if x["id"] not in self.module_of:
                reach = x["id"] in linked or (x.get("slug") and x["slug"] in linked)
                self.add(name, "warning", x,
                         "published but in no module, so students cannot find it from the Modules page"
                         + (" (another page links to it)" if reach else " and nothing links to it"),
                         f'{x["_kind"]} "{x["title"]}"')
        self.status[name] = f"run: {checked} published items"

    def c6_module_week_drift(self):
        name = "6 Module week and due week disagree"
        if not self.first_day or not self.tz_known:
            return self.not_run(name, "the course start date or time zone is unknown")
        checked = 0
        for item in self.dated:
            mod = self.module_of.get(item["id"])
            mweek = self.module_week(mod)
            due = local_date(item)
            if not mweek or not due:
                continue
            checked += 1
            dweek = self.week_of(due)
            if dweek - mweek > 1:
                self.add(name, "warning", item,
                         f"sits in the week {mweek} module but is due in week {dweek} ({human(due)})",
                         f'module "{mod["title"]}"')
        self.status[name] = f"run: {checked} dated items placed in week modules"

    def c7_revision_gap(self):
        name = "7 Draft-to-final gap"
        if not self.tz_known:
            return self.not_run(name, "the course time zone could not be inferred")
        stems = {}
        for item in self.dated:
            t = norm(item["title"])
            role = "draft" if re.search(r"\b(draft|rough)\b", t) else "final" if re.search(r"\b(final|revised|revision)\b", t) else None
            if not role:
                continue
            stem = re.sub(r"\b(draft|rough|final|revised|revision)\b|\b\d+\b", " ", t)
            stems.setdefault(" ".join(stem.split()), {}).setdefault(role, []).append(item)
        pairs = 0
        for stem, roles in stems.items():
            for draft in roles.get("draft", []):
                for final in roles.get("final", []):
                    pairs += 1
                    gap = (local_date(final) - local_date(draft)).days
                    if gap < REVISION_GAP_DAYS:
                        self.add(name, "warning", final,
                                 f'due {gap} days after "{draft["title"]}"; fewer than {REVISION_GAP_DAYS} days leaves little time to return feedback and revise',
                                 f"draft {human(local_date(draft))}, final {human(local_date(final))}")
        self.status[name] = f"run: {pairs} draft and final pairs"

    def c8_due_on_cancelled_day(self):
        name = "8 Due on a cancelled class day"
        if not self.sessions:
            return self.not_run(name, "the class meeting pattern could not be inferred")
        cancelled = {s["date"]: s for s in self.sessions if s["cancelled"]}
        for item in self.dated:
            due = local_date(item)
            if due and due.isoformat() in cancelled:
                self.add(name, "info", item, f"due {human(due)}, a day class does not meet",
                         cancelled[due.isoformat()].get("cancelled_evidence", ""))
        self.status[name] = f"run: {len(cancelled)} cancelled meetings"

    def c9_unpublished_dated(self):
        name = "9 Dated work unpublished"
        hidden = [x for x in self.dated if (x.get("workflow_state") or "") not in ("active", "published")]
        later = []
        for item in sorted(hidden, key=local_date):
            due = local_date(item)
            days = (due - self.as_of).days
            if days < 0:
                self.add(name, "warning", item,
                         f"was due {human(due)}, before {human(self.as_of)}, and is still unpublished, so students never saw it",
                         "unpublished in this export")
            elif days <= LEAD_DAYS:
                self.add(name, "warning", item,
                         f"is due {human(due)}, {days} day(s) after {human(self.as_of)}, and students cannot see it yet",
                         "unpublished in this export")
            else:
                later.append(item)
        if later:
            self.add(name, "info", None,
                     f"{len(later)} more dated items are unpublished and due more than {LEAD_DAYS} days after {human(self.as_of)}, "
                     f"the earliest {human(local_date(later[0]))}. That is normal for a course opened one week at a time",
                     "; ".join(x["title"] for x in later))
        self.status[name] = f"run: {len(hidden)} of {len(self.dated)} dated items unpublished, counted from {human(self.as_of)}"

    def c10_live_course_links(self):
        name = "10 Links into a specific Canvas course"
        n = 0
        for x in self.items + [dict(SYLLABUS, links=self.m["syllabus"].get("links", []))]:
            for link in x.get("links", []):
                if link["kind"] == "canvas_course_url":
                    n += 1
                    self.add(name, "warning", x,
                             "links to a page inside one particular Canvas course by its address; the link keeps pointing at that course after this one is copied to a new term",
                             link["href"])
        self.status[name] = f"run: {n} found"

    def run(self):
        for check in (self.c1_date_drift, self.c2_dead_links, self.c3_due_before_taught, self.c4_nothing_to_grade,
                      self.c5_not_in_module, self.c6_module_week_drift, self.c7_revision_gap,
                      self.c8_due_on_cancelled_day, self.c9_unpublished_dated, self.c10_live_course_links):
            check()
        # One finding per (check, item, message): the same sentence can appear on several pages.
        seen, unique = set(), []
        for f in self.findings:
            key = (f["check"], f["item_id"], f["message"])
            if key not in seen:
                seen.add(key)
                unique.append(f)
        unique.sort(key=lambda f: (SEVERITY_ORDER[f["severity"]], int(f["check"].split()[0]), f["item"] or ""))
        for i, f in enumerate(unique, 1):
            f["id"] = f"F{i}"
        self.findings = unique
        return self


# ---------------------------------------------------------------- graph

def build_graph(model, checker):
    nodes, edges = [], []
    weeks = sorted({s["week"] for s in model["sessions"]})
    for w in weeks:
        nodes.append({"id": f"week:{w}", "type": "week", "label": f"Week {w}"})
    for s in model["sessions"]:
        sid = f"meeting:{s['date']}"
        nodes.append({"id": sid, "type": "meeting", "label": f"{s['weekday']} {s['date']}",
                      "date": s["date"], "cancelled": s["cancelled"]})
        edges.append({"from": f"week:{s['week']}", "to": sid, "type": "has_meeting"})
    for mod in model["modules"]:
        mid = f"module:{mod['id']}"
        nodes.append({"id": mid, "type": "module", "label": mod["title"], "position": mod["position"]})
        w = checker.module_week(mod)
        if w and f"week:{w}" in {n["id"] for n in nodes}:
            edges.append({"from": mid, "to": f"week:{w}", "type": "covers_week"})
        for it in mod["items"]:
            if it.get("ref") in checker.by_id:
                edges.append({"from": mid, "to": f"item:{it['ref']}", "type": "contains"})
    for x in checker.items:
        node = {"id": f"item:{x['id']}", "type": x["_kind"], "label": x["title"],
                "published": (x.get("workflow_state") or "") in ("active", "published")}
        if x.get("due_local"):
            node["due_local"] = x["due_local"]
            d = local_date(x)
            w = checker.week_of(d)
            if w:
                edges.append({"from": f"item:{x['id']}", "to": f"week:{w}", "type": "due_in_week"})
        nodes.append(node)
        for link in x.get("links", []):
            target = (link.get("target") or "").split("#")[0]
            hit = checker.by_id.get(target) or checker.page_by_slug.get(target)
            if hit and hit["id"] != x["id"]:
                edges.append({"from": f"item:{x['id']}", "to": f"item:{hit['id']}", "type": "links_to"})
    unique = {(e["from"], e["to"], e["type"]): e for e in edges}
    return {"nodes": nodes, "edges": list(unique.values())}


# ---------------------------------------------------------------- report

def report(model, checker):
    inf = model["inferred"]
    sev = {k: sum(f["severity"] == k for f in checker.findings) for k in ("defect", "warning", "info")}
    out = [f"# Sequence report: {model['course']['title'] or model['source']['file']}", "",
           f"Read from `{model['source']['file']}`. {sev['defect']} defects, {sev['warning']} warnings, "
           f"{sev['info']} notes.", "", "## Assumptions", "",
           "These facts are not stored in a Canvas export. They were inferred, and every date check below depends on them.", ""]
    for label, key in (("Time zone", "time_zone"), ("Class meetings", "meetings"), ("Last day of term", "term_end")):
        f = inf[key]
        v = f["value"]
        if isinstance(v, dict):
            v = f"{'/'.join(v['days'])} {v['start']}-{v['end']}"
        out.append(f"- **{label}:** {v if v is not None else 'unknown'} ({f['confidence']} confidence). {f['evidence']}.")
    cancelled = [s for s in model["sessions"] if s["cancelled"]]
    out.append(f"- **Counted from:** {human(checker.as_of)}, the day the export was read. Deadlines \"due soon\" are measured from this date.")
    out.append(f"- **Cancelled meetings:** " + (", ".join(human(dt.date.fromisoformat(s['date'])) for s in cancelled) or "none found") + ".")
    out += ["", "If any of these is wrong, rerun the reader with a settings file (see the reading-canvas-exports skill).", "",
            "## Checks", "", "| # | Check | Result |", "|---|---|---|"]
    for name in sorted(checker.status, key=lambda n: int(n.split()[0])):
        n, title = name.split(" ", 1)
        found = sum(f["check"] == name for f in checker.findings)
        out.append(f"| {n} | {title} | {checker.status[name]}; {found} finding(s) |")
    out += ["", "## Findings", ""]
    if not checker.findings:
        out.append("No findings.")
    for f in checker.findings:
        label = f"page \"{f['item']}\"" if f.get("kind") == "page" else (f['item'] or 'Course')
        out.append(f"{f['id']}. **{f['severity'].capitalize()}, check {f['check'].split()[0]}.** "
                   f"{label}: {f['message']}. Evidence: {f['evidence']}")
    out += ["", "## Timeline", "",
            "One row per week of the term: the meetings, the week's modules, and what is due.", "",
            "| Week | Meetings | Modules | Due |", "|---|---|---|---|"]
    weeks = sorted({s["week"] for s in model["sessions"]}) or sorted(
        {checker.week_of(local_date(x)) for x in checker.dated if checker.week_of(local_date(x))})
    for w in weeks:
        meets = ", ".join((f"~~{s['weekday']} {s['date'][5:]}~~" if s["cancelled"] else f"{s['weekday']} {s['date'][5:]}")
                          for s in model["sessions"] if s["week"] == w)
        mods = "; ".join(m["title"] for m in model["modules"] if checker.module_week(m) == w)
        due = "; ".join(f"{x['title']} ({DAYS[local_date(x).weekday()]})" for x in
                        sorted(checker.dated, key=local_date) if checker.week_of(local_date(x)) == w)
        out.append(f"| {w} | {meets or '—'} | {mods or '—'} | {due or '—'} |")
    out += ["", "## What this report does not check", "",
            "- Whether the content of a page actually teaches what an assignment asks for. Placement in a module is used as the evidence of when something is taught.",
            "- Anything said in class but not written in the course.",
            "- Calendar events and announcements, which Canvas does not include in a course export.",
            "- Student data of any kind.", ""]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Check a Canvas course's sequence and build its graph")
    ap.add_argument("input", help="course_model.json, or a .imscc export")
    ap.add_argument("--out-dir", help="where to write the three output files (default: beside the input)")
    ap.add_argument("--fail-on", choices=["defect", "warning"], help="exit 1 if any finding is this severe")
    ap.add_argument("--as-of", help="YYYY-MM-DD to count deadlines from (default: the day the export was read)")
    args = ap.parse_args(argv)
    src = pathlib.Path(args.input)
    out_dir = pathlib.Path(args.out_dir) if args.out_dir else src.resolve().parent
    out_dir.mkdir(parents=True, exist_ok=True)
    if src.suffix.lower() == ".imscc":
        if not READER.exists():
            print("error: given an .imscc, but the reading-canvas-exports skill is not installed beside this one. "
                  "Run it first and pass course_model.json.", file=sys.stderr)
            return 2
        model_path = out_dir / "course_model.json"
        done = subprocess.run([sys.executable, str(READER), str(src), "--out", str(model_path)])
        if done.returncode:
            return done.returncode
        src = model_path
    try:
        model = json.loads(src.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read {src}: {exc}", file=sys.stderr)
        return 2
    if not str(model.get("schema_version", "")).startswith("1.") or "links" not in model.get("syllabus", {}):
        print("error: this course_model.json is from an older reader. Rerun the reading-canvas-exports skill.", file=sys.stderr)
        return 2
    try:
        as_of = dt.date.fromisoformat(args.as_of) if args.as_of else None
    except ValueError:
        print(f"error: --as-of must be YYYY-MM-DD, not {args.as_of}", file=sys.stderr)
        return 2
    checker = Checker(model, as_of).run()
    (out_dir / "sequence_report.md").write_text(report(model, checker), encoding="utf-8")
    (out_dir / "sequence_findings.json").write_text(json.dumps(
        {"status": checker.status, "findings": checker.findings}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    (out_dir / "course_graph.json").write_text(json.dumps(build_graph(model, checker), indent=2, ensure_ascii=False) + "\n",
                                               encoding="utf-8")
    sev = {k: sum(f["severity"] == k for f in checker.findings) for k in ("defect", "warning", "info")}
    print(f"{sev['defect']} defects, {sev['warning']} warnings, {sev['info']} notes")
    for name in sorted(checker.status, key=lambda n: int(n.split()[0])):
        print(f"  {name}: {checker.status[name]}")
    print(f"Wrote {out_dir / 'sequence_report.md'}, sequence_findings.json and course_graph.json")
    if args.fail_on and any(SEVERITY_ORDER[f["severity"]] <= SEVERITY_ORDER[args.fail_on] for f in checker.findings):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
