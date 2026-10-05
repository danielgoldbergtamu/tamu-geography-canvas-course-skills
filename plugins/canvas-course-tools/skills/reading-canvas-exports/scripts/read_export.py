#!/usr/bin/env python3
"""Read a Canvas course export (.imscc) into one course_model.json file.

Usage:
    python3 read_export.py COURSE.imscc [--out course_model.json] [--settings overrides.json]

The output is the input every other skill in this plugin reads. Its format is
documented in references/course-model.md.

Facts Canvas does not export (the course time zone, the days and times the class
meets, the term's last day) are INFERRED, never asked for. Each inferred fact is
recorded with its value, where it came from, the text or numbers it was read from,
and a confidence of high, medium or low. A fact that cannot be inferred is recorded
as null with the reason, and the skills that need it report those checks as not run.
An optional --settings file overrides any inferred fact; nobody is required to write
one.

Standard library only. Python 3.10 or later.
"""
import argparse
import datetime as dt
import hashlib
import html
import html.parser
import json
import pathlib
import re
import sys
import xml.etree.ElementTree as ET
import zipfile

SCHEMA_VERSION = "1.0"

# Time zones tried when inferring the course's zone. Canvas exports store every
# date in UTC with no zone, so the zone is chosen by testing which candidate puts
# deadlines on round local times. US zones first because that is where this was
# built and tested; the rest cover the most common non-US Canvas institutions.
CANDIDATE_ZONES = [
    "America/New_York", "America/Chicago", "America/Denver", "America/Phoenix",
    "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu",
    "America/Puerto_Rico", "America/Toronto", "America/Vancouver",
    "Europe/London", "Europe/Berlin", "Australia/Sydney", "Pacific/Auckland",
]

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Day tokens as instructors write them in syllabi, mapped to weekday numbers.
DAY_TOKENS = {
    "m": [0], "mon": [0], "monday": [0], "mondays": [0],
    "t": [1], "tu": [1], "tue": [1], "tues": [1], "tuesday": [1], "tuesdays": [1],
    "w": [2], "wed": [2], "weds": [2], "wednesday": [2], "wednesdays": [2],
    "r": [3], "th": [3], "thu": [3], "thur": [3], "thurs": [3], "thursday": [3], "thursdays": [3],
    "f": [4], "fri": [4], "friday": [4], "fridays": [4],
    "s": [5], "sa": [5], "sat": [5], "saturday": [5], "su": [6], "sun": [6], "sunday": [6],
    "tr": [1, 3], "tth": [1, 3], "mw": [0, 2], "mwf": [0, 2, 4], "mtwr": [0, 1, 2, 3],
    "mtwrf": [0, 1, 2, 3, 4], "wf": [2, 4], "mf": [0, 4],
}
TIME_RE = r"(\d{1,2})(?::(\d{2}))?\s*([ap])?\.?\s*m?\.?"
RANGE_RE = re.compile(TIME_RE + r"\s*(?:-|–|—|to)\s*" + TIME_RE, re.I)
DAYS_RE = re.compile(
    r"\b((?:mon|tue|tues|wed|weds|thu|thur|thurs|fri|sat|sun)[a-z]*s?"
    r"|m|t|w|r|f|tu|th|tr|tth|mw|mwf|mtwr|mtwrf|wf|mf)\b"
    r"(?:\s*(?:/|,|&|and|\+|-)\s*\b((?:mon|tue|tues|wed|weds|thu|thur|thurs|fri|sat|sun)[a-z]*s?|m|t|w|r|f|tu|th)\b)*",
    re.I)
# Lines that state meeting times for something other than the class itself.
NOT_CLASS = re.compile(r"office\s*hours?|help\s*session|tutor|review\s*session|exam\s*period|final\s*exam|drop[- ]?in|consult", re.I)
CLASS_CUES = re.compile(r"\b(class|lecture|meeting|meets|meet|section|course\s*time|schedule|lab|studio|seminar|time\s*and\s*place|when)\b", re.I)


class ExportError(Exception):
    """The file is not a Canvas export this reader can use. The message says why."""


# ---------------------------------------------------------------- XML helpers

def strip_ns(root):
    for el in root.iter():
        if isinstance(el.tag, str) and "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]
        for key in list(el.attrib):
            if "}" in key:
                el.attrib[key.split("}", 1)[1]] = el.attrib.pop(key)
    return root


def parse_xml(zf, name):
    try:
        return strip_ns(ET.fromstring(zf.read(name)))
    except KeyError:
        return None
    except ET.ParseError as exc:
        raise ExportError(f"{name} is not valid XML: {exc}") from exc


def text(el, tag, default=None):
    if el is None:
        return default
    found = el.find(tag)
    if found is None or found.text is None:
        return default
    value = found.text.strip()
    return value if value != "" else default


def number(value):
    try:
        return float(value) if value not in (None, "") else None
    except ValueError:
        return None


def boolean(value):
    return None if value is None else value.strip().lower() == "true"


class _TextExtractor(html.parser.HTMLParser):
    BLOCK = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "table", "ul", "ol", "section"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.skip = [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def html_text(raw):
    if not raw:
        return ""
    parser = _TextExtractor()
    parser.feed(raw)
    lines = [re.sub(r"[ \t ]+", " ", line).strip() for line in "".join(parser.parts).splitlines()]
    return "\n".join(line for line in lines if line)


def html_meta(raw):
    meta = dict(re.findall(r'<meta\s+name="([^"]+)"\s+content="([^"]*)"', raw or ""))
    title = re.search(r"<title>(.*?)</title>", raw or "", re.S)
    meta["title"] = html.unescape(title.group(1).strip()) if title else None
    return meta


def read_html(zf, name):
    try:
        return zf.read(name).decode("utf-8", errors="replace")
    except KeyError:
        return None


# ---------------------------------------------------------------- dates

def utc(value):
    """Canvas writes dates as naive UTC ('2026-09-11T04:59:00'). Return an aware datetime."""
    if not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def iso(value):
    return value.isoformat() if value else None


class _RuleZone(dt.tzinfo):
    """A time zone from a standard offset and a daylight-saving rule.

    Used only when Python has no time-zone database, which is the normal state of
    Python on Windows unless the 'tzdata' package is installed. Covers the rules in
    _RULES below, which are correct for 2007 onward in North America and 1996 onward
    in the European Union.
    """

    def __init__(self, name, std_hours, rule):
        self.name, self.std, self.rule = name, dt.timedelta(hours=std_hours), rule

    @staticmethod
    def _nth_sunday(year, month, n):
        first = dt.date(year, month, 1)
        day = first + dt.timedelta(days=(6 - first.weekday()) % 7)
        return day + dt.timedelta(weeks=n - 1)

    @staticmethod
    def _last_sunday(year, month):
        nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
        last = nxt - dt.timedelta(days=1)
        return last - dt.timedelta(days=(last.weekday() + 1) % 7)

    def _dst_window_utc(self, year):
        if self.rule == "us":    # second Sunday of March to first Sunday of November, 2:00 local
            start = dt.datetime.combine(self._nth_sunday(year, 3, 2), dt.time(2)) - self.std
            end = dt.datetime.combine(self._nth_sunday(year, 11, 1), dt.time(2)) - self.std - dt.timedelta(hours=1)
            return start, end
        if self.rule == "eu":    # last Sunday of March to last Sunday of October, 1:00 UTC
            return (dt.datetime.combine(self._last_sunday(year, 3), dt.time(1)),
                    dt.datetime.combine(self._last_sunday(year, 10), dt.time(1)))
        return None

    def _in_dst_utc(self, naive_utc):
        window = self._dst_window_utc(naive_utc.year)
        return bool(window) and window[0] <= naive_utc < window[1]

    def fromutc(self, when):
        naive = when.replace(tzinfo=None)
        if self._in_dst_utc(naive):
            return (naive + self.std + dt.timedelta(hours=1)).replace(tzinfo=self)
        local = (naive + self.std).replace(tzinfo=self)
        # The hour repeated when daylight saving ends: the second pass gets fold=1.
        if self._in_dst_utc(naive - dt.timedelta(hours=1)):
            local = local.replace(fold=1)
        return local

    def utcoffset(self, when):
        if when is None:
            return self.std
        naive = when.replace(tzinfo=None)
        as_dst = self._in_dst_utc(naive - self.std - dt.timedelta(hours=1))
        as_std = self._in_dst_utc(naive - self.std)
        if as_dst and as_std:
            dst_now = True
        elif as_dst and not as_std:      # repeated hour: fold picks which pass
            dst_now = getattr(when, "fold", 0) == 0
        elif not as_dst and as_std:      # skipped hour in spring: treat as standard
            dst_now = False
        else:
            dst_now = False
        return self.std + (dt.timedelta(hours=1) if dst_now else dt.timedelta(0))

    def dst(self, when):
        return self.utcoffset(when) - self.std

    def tzname(self, when):
        return self.name


# Standard offset in hours and daylight-saving rule, for the fallback only. Each
# entry was checked hour by hour against the IANA database for 2025-2027 and agreed
# at every instant. Zones whose rules are changing (British Columbia moved to
# permanent daylight time in November 2026) are left out on purpose: a hand-written
# rule would be silently wrong, and with no database they are reported as unknown.
_RULES = {
    "America/New_York": (-5, "us"), "America/Toronto": (-5, "us"), "America/Chicago": (-6, "us"),
    "America/Denver": (-7, "us"), "America/Phoenix": (-7, None), "America/Los_Angeles": (-8, "us"),
"America/Anchorage": (-9, "us"), "Pacific/Honolulu": (-10, None),
    "America/Puerto_Rico": (-4, None), "Europe/London": (0, "eu"), "Europe/Berlin": (1, "eu"),
}


def zone(name):
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(name)
    except Exception:  # zoneinfo missing, or no tz database (Windows without tzdata)
        if name in _RULES:
            return _RuleZone(name, *_RULES[name])
        return None


def infer_time_zone(dated, start_at, overrides):
    """Choose the zone that puts the course's deadlines on round local times."""
    if overrides.get("time_zone"):
        return _fact(overrides["time_zone"], "settings file", "set by the user", "high")
    if not dated:
        return _fact(None, "none", "the export has no dated items", "low",
                     reason="no due, unlock or lock dates to test against")
    scores = []
    for name in CANDIDATE_ZONES:
        tz = zone(name)
        if tz is None:
            continue
        round_hits = 0
        for when in dated:
            local = when.astimezone(tz)
            if (local.hour, local.minute) in ((23, 59), (0, 0)) or local.minute in (0, 30, 59):
                round_hits += 1
        start_hit = 0
        if start_at:
            local = start_at.astimezone(tz)
            start_hit = 1 if (local.hour, local.minute) == (0, 0) else 0
        scores.append(((round_hits / len(dated)) + 0.25 * start_hit, name, round_hits))
    if not scores:
        return _fact(None, "none", "no time-zone database is available on this computer", "low",
                     reason="install the 'tzdata' Python package, or set time_zone in a settings file")
    scores.sort(reverse=True)
    best, runner = scores[0], (scores[1] if len(scores) > 1 else (0, None, 0))
    evidence = (f"{best[2]} of {len(dated)} dated items fall on a round local time in {best[1]}"
                + (", and the course start date is local midnight" if best[0] - best[2] / len(dated) > 0 else ""))
    tied = [s[1] for s in scores if abs(s[0] - best[0]) < 1e-9]
    if len(tied) > 1:
        return _fact(best[1], "inferred from due dates", evidence + f"; tied with {', '.join(tied[1:])}", "medium")
    confidence = "high" if best[0] >= 0.8 and best[0] - runner[0] >= 0.15 else "medium" if best[0] >= 0.5 else "low"
    return _fact(best[1], "inferred from due dates", evidence, confidence)


def to_local(when, tz_name):
    if not when:
        return None
    tz = zone(tz_name) if tz_name else None
    return when.astimezone(tz) if tz else when


def _fact(value, source, evidence, confidence, reason=None):
    out = {"value": value, "source": source, "evidence": evidence, "confidence": confidence}
    if value is None and reason:
        out["reason"] = reason
    return out


# ---------------------------------------------------------------- meetings

def _clock(hour, minute, ampm, partner_ampm):
    hour, minute = int(hour), int(minute or 0)
    ampm = (ampm or partner_ampm or "").lower()
    if ampm == "p" and hour < 12:
        hour += 12
    elif ampm == "a" and hour == 12:
        hour = 0
    elif not ampm and 1 <= hour <= 6:  # "1:30-2:45" with no am/pm is an afternoon class
        hour += 12
    return hour, minute


def _days(match_text):
    days = set()
    for token in re.split(r"[\s/,&+()\[\]:;]+|\band\b|-", match_text.lower()):
        token = token.strip().strip(".")
        if token in DAY_TOKENS:
            days.update(DAY_TOKENS[token])
        elif token[:3] in DAY_TOKENS and len(token) > 3:
            days.update(DAY_TOKENS[token[:3]])
    return sorted(days)


def infer_meetings(syllabus_text, overrides):
    if overrides.get("meetings"):
        m = overrides["meetings"]
        return _fact(m, "settings file", "set by the user", "high")
    candidates = []
    lines = [l for l in (syllabus_text or "").splitlines() if l.strip()]
    for i, line in enumerate(lines):
        context = " ".join(lines[max(0, i - 1): i + 1])
        for rng in RANGE_RE.finditer(line):
            before = line[:rng.start()]
            day_match = None
            for dm in DAYS_RE.finditer(before[-40:]):
                day_match = dm
            if not day_match:
                continue
            days = _days(day_match.group(0))
            if not days:
                continue
            h1, m1, a1, h2, m2, a2 = rng.groups()
            # A clock range, not a phone number or a page range: real hours and
            # minutes, and a colon or am/pm on at least one end.
            if not (m1 or m2 or a1 or a2):
                continue
            if not (1 <= int(h1) <= 24 and 1 <= int(h2) <= 24
                    and int(m1 or 0) < 60 and int(m2 or 0) < 60):
                continue
            start = _clock(h1, m1, a1, a2)
            end = _clock(h2, m2, a2, a1)
            if end <= start:
                continue
            excluded = bool(NOT_CLASS.search(context))
            cue = bool(CLASS_CUES.search(context))
            candidates.append({
                "days": [DAY_NAMES[d] for d in days],
                "start": f"{start[0]:02d}:{start[1]:02d}",
                "end": f"{end[0]:02d}:{end[1]:02d}",
                "evidence": line.strip()[:200],
                "excluded": excluded,
                "cue": cue,
            })
    usable = [c for c in candidates if not c["excluded"]]
    if not usable:
        why = ("the syllabus states times only for office hours or similar"
               if candidates else "the syllabus states no days with a time range")
        return _fact(None, "none", why, "low", reason=why)
    usable.sort(key=lambda c: (not c["cue"], candidates.index(c)))
    best = usable[0]
    distinct = {(tuple(c["days"]), c["start"], c["end"]) for c in usable}
    confidence = "high" if best["cue"] and len(distinct) == 1 else "medium"
    value = {k: best[k] for k in ("days", "start", "end")}
    evidence = f'syllabus line "{best["evidence"]}"'
    skipped = [c["evidence"] for c in candidates if c["excluded"]]
    if skipped:
        evidence += f'; ignored as not class time: {"; ".join(repr(s[:80]) for s in skipped[:3])}'
    if len(distinct) > 1:
        evidence += f"; {len(distinct) - 1} other day-and-time pattern(s) also found"
    return _fact(value, "inferred from the syllabus", evidence, confidence)


def meeting_dates(meetings, first_day, last_day):
    if not meetings or not first_day or not last_day:
        return []
    wanted = {DAY_NAMES.index(d) for d in meetings["days"]}
    out, day, week_start = [], first_day, first_day - dt.timedelta(days=first_day.weekday())
    while day <= last_day:
        if day.weekday() in wanted:
            week = (day - week_start).days // 7 + 1
            out.append({"date": day.isoformat(), "weekday": DAY_NAMES[day.weekday()], "week": week,
                        "start": meetings["start"], "end": meetings["end"]})
        day += dt.timedelta(days=1)
    return out


# ---------------------------------------------------------------- cancellations

NO_CLASS = re.compile(r"\bno\s+class(es)?\b|\bclass(es)?\s+(is\s+|are\s+)?cancel+ed\b|\bholiday\b|"
                      r"\bthanksgiving\b|\b(spring|fall|winter|mid-?term)\s+break\b|\breading\s+day\b|"
                      r"\bno\s+meeting\b|\buniversity\s+closed\b", re.I)
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
DATE_RE = re.compile(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|sept|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b|\b(\d{1,2})/(\d{1,2})(?:/\d{2,4})?\b", re.I)


class _Tables(html.parser.HTMLParser):
    """Collect every table in an HTML document as rows of cell text."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self.row, self.cell, self.depth = [], None, None, 0

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self.depth += 1
            self.tables.append([])
        elif tag == "tr" and self.depth:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []
        elif tag in ("br", "p", "div", "li") and self.cell is not None:
            self.cell.append(" ")

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell is not None and self.row is not None:
            self.row.append(re.sub(r"\s+", " ", "".join(self.cell)).strip())
            self.cell = None
        elif tag == "tr" and self.row is not None and self.depth:
            self.tables[-1].append(self.row)
            self.row = None
        elif tag == "table" and self.depth:
            self.depth -= 1

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def _dates_in(textval, year_hint):
    out = []
    for m in DATE_RE.finditer(textval):
        try:
            if m.group(1):
                month, day = MONTHS[m.group(1).lower()[:3]], int(m.group(2))
            else:
                month, day = int(m.group(3)), int(m.group(4))
            year = year_hint
            out.append(dt.date(year, month, day))
        except (ValueError, KeyError):
            continue
    return out


def _weekday_of_header(cell):
    # A column of deadlines is not a column of class meetings.
    if len(cell) >= 40 or re.search(r"\bdue\b|deadline|submit", cell, re.I):
        return None
    days = _days(cell)
    return days[0] if len(days) == 1 else None


def find_cancellations(syllabus_raw, sessions):
    """Return {session date: evidence} for meetings the syllabus says will not happen."""
    if not sessions or not syllabus_raw:
        return {}
    by_date = {s["date"]: s for s in sessions}
    first = dt.date.fromisoformat(sessions[0]["date"])
    last = dt.date.fromisoformat(sessions[-1]["date"])

    def resolve(d):
        # A term crossing New Year: a date that lands before the term in this year
        # belongs to the next one.
        if d < first - dt.timedelta(days=7):
            try:
                d = d.replace(year=d.year + 1)
            except ValueError:
                pass
        return d

    def week_of(d):
        start = d - dt.timedelta(days=d.weekday())
        return [s for s in sessions if start <= dt.date.fromisoformat(s["date"]) < start + dt.timedelta(days=7)]

    found = {}
    parser = _Tables()
    parser.feed(syllabus_raw)
    for table in parser.tables:
        if not table:
            continue
        header = table[0]
        col_day = {i: _weekday_of_header(c) for i, c in enumerate(header)}
        for row in table[1:]:
            joined = " | ".join(row)
            if not NO_CLASS.search(joined):
                continue
            dates = [resolve(d) for d in _dates_in(joined, first.year)]
            dates = [d for d in dates if first - dt.timedelta(days=7) <= d <= last + dt.timedelta(days=7)]
            if not dates:
                continue
            week = week_of(dates[0])
            day_cells = [(col_day.get(i), c) for i, c in enumerate(row) if col_day.get(i) is not None]
            if day_cells:
                for weekday, cell in day_cells:
                    if NO_CLASS.search(cell):
                        for s in week:
                            if DAY_NAMES.index(s["weekday"]) == weekday:
                                found.setdefault(s["date"], f'syllabus table row "{joined[:160]}"')
            else:
                exact = [d.isoformat() for d in dates if d.isoformat() in by_date]
                targets = exact or [s["date"] for s in week]
                for t in targets:
                    found.setdefault(t, f'syllabus table row "{joined[:160]}"')
    # Plain lines outside tables: a no-class line that names a date cancels that date.
    for line in html_text(re.sub(r"(?is)<table.*?</table>", " ", syllabus_raw)).splitlines():
        if NO_CLASS.search(line):
            for d in (resolve(x) for x in _dates_in(line, first.year)):
                if d.isoformat() in by_date:
                    found.setdefault(d.isoformat(), f'syllabus line "{line.strip()[:160]}"')
    return found


# ---------------------------------------------------------------- readers

def read_manifest(zf):
    root = parse_xml(zf, "imsmanifest.xml")
    if root is None:
        raise ExportError("the file has no imsmanifest.xml, so it is not an IMS Common Cartridge")
    resources = {}
    for res in root.iter("resource"):
        files = [f.get("href") for f in res.findall("file") if f.get("href")]
        resources[res.get("identifier")] = {
            "type": res.get("type"), "href": res.get("href") or (files[0] if files else None),
            "files": files, "intendeduse": res.get("intendeduse"),
            "dependencies": [d.get("identifierref") for d in res.findall("dependency")],
        }
    return resources


def read_assignment(zf, folder, settings_name, tz_name):
    a = parse_xml(zf, settings_name)
    html_name = next((n for n in zf.namelist() if n.startswith(folder + "/") and n.endswith(".html")), None)
    raw = read_html(zf, html_name) if html_name else None
    due = utc(text(a, "due_at"))
    return {
        "id": a.get("identifier") or folder,
        "kind": "assignment",
        "title": text(a, "title"),
        "due_at_utc": iso(due),
        "due_local": iso(to_local(due, tz_name)),
        "unlock_at_utc": iso(utc(text(a, "unlock_at"))),
        "lock_at_utc": iso(utc(text(a, "lock_at"))),
        "points_possible": number(text(a, "points_possible")),
        "grading_type": text(a, "grading_type"),
        "submission_types": [s for s in (text(a, "submission_types", "") or "").split(",") if s],
        "assignment_group": text(a, "assignment_group_identifierref"),
        "workflow_state": text(a, "workflow_state"),
        "rubric": text(a, "rubric_identifierref"),
        "rubric_used_for_grading": boolean(text(a, "rubric_use_for_grading")),
        "peer_reviews": boolean(text(a, "peer_reviews")),
        "peer_review_count": int(number(text(a, "peer_review_count")) or 0),
        "omit_from_final_grade": boolean(text(a, "omit_from_final_grade")),
        "position": int(number(text(a, "position")) or 0) or None,
        "href": html_name,
        "text": html_text(raw),
    }


def read_quiz(zf, folder, meta_name, resources, tz_name):
    q = parse_xml(zf, meta_name)
    inner = q.find("assignment")
    due = utc(text(q, "due_at") or text(inner, "due_at"))
    questions = None
    for qti in (folder + "/assessment_qti.xml",):
        try:
            questions = zf.read(qti).decode("utf-8", errors="replace").count("<item ")
        except KeyError:
            pass
    return {
        "id": q.get("identifier") or folder,
        "kind": "quiz",
        "title": text(q, "title"),
        "quiz_type": text(q, "quiz_type"),
        "due_at_utc": iso(due),
        "due_local": iso(to_local(due, tz_name)),
        "unlock_at_utc": iso(utc(text(q, "unlock_at"))),
        "lock_at_utc": iso(utc(text(q, "lock_at"))),
        "points_possible": number(text(q, "points_possible")),
        "assignment_group": text(q, "assignment_group_identifierref") or text(inner, "assignment_group_identifierref"),
        "workflow_state": text(q, "workflow_state") or text(inner, "workflow_state"),
        "question_count": questions,
        "text": html_text(text(q, "description")),
    }


def read_discussion(zf, ident, res, resources):
    # Common Cartridge discussions: an imsdt topic file plus a Canvas topicMeta file
    # that depends on it. Written from the published spec; see references.
    topic = parse_xml(zf, res["files"][0]) if res["files"] else None
    meta = None
    for other_id, other in resources.items():
        if ident in other["dependencies"] and other["files"]:
            meta = parse_xml(zf, other["files"][0])
    title = text(topic, "title") or text(meta, "title")
    kind = "announcement" if (text(meta, "type") or "").lower() == "announcement" else "discussion"
    return {"id": ident, "kind": kind, "title": title,
            "workflow_state": text(meta, "workflow_state"),
            "assignment": text(meta.find("assignment"), "title") if meta is not None and meta.find("assignment") is not None else None,
            "text": html_text(text(topic, "text"))}


def read_rubrics(zf):
    root = parse_xml(zf, "course_settings/rubrics.xml")
    out = []
    for r in ([] if root is None else root.findall("rubric")):
        criteria = []
        for c in r.iter("criterion"):
            criteria.append({
                "id": text(c, "criterion_id"),
                "description": text(c, "description"),
                "long_description": html_text(text(c, "long_description")),
                "points": number(text(c, "points")),
                "mastery_points": number(text(c, "mastery_points")),
                "ignore_for_scoring": boolean(text(c, "ignore_for_scoring")),
                "outcome": text(c, "learning_outcome_identifierref"),
                "outcome_external_id": text(c, "learning_outcome_external_identifier"),
                "ratings": [{"description": text(x, "description"), "points": number(text(x, "points")),
                             "long_description": html_text(text(x, "long_description"))}
                            for x in c.iter("rating")],
            })
        out.append({
            "id": r.get("identifier"), "title": text(r, "title"),
            "points_possible": number(text(r, "points_possible")),
            "free_form_criterion_comments": boolean(text(r, "free_form_criterion_comments")),
            "criteria": criteria,
        })
    return out


def read_outcomes(zf):
    root = parse_xml(zf, "course_settings/learning_outcomes.xml")
    groups, outcomes = [], []

    def walk(node, group_id):
        for child in node:
            if child.tag == "learningOutcomeGroup":
                gid = child.get("identifier")
                groups.append({"id": gid, "title": text(child, "title"), "parent": group_id,
                               "source_outcome_group_id": text(child, "source_outcome_group_id")})
                container = child.find("learningOutcomes")
                if container is not None:
                    walk(container, gid)
            elif child.tag == "learningOutcome":
                copied = text(child, "copied_from_outcome_id")
                external = text(child, "external_identifier")
                outcomes.append({
                    "id": child.get("identifier"), "title": text(child, "title"),
                    "description": html_text(text(child, "description")),
                    "group": group_id,
                    "external_identifier": external,
                    "copied_from_outcome_id": copied,
                    "is_global": boolean(text(child, "is_global_outcome")),
                    "mastery_points": number(text(child, "mastery_points")),
                    "points_possible": number(text(child, "points_possible")),
                    "alignments": [{"content_type": text(a, "content_type"), "content_id": text(a, "content_id")}
                                   for a in child.iter("alignment")],
                })
            elif child.tag == "learningOutcomes":
                walk(child, group_id)

    if root is not None:
        walk(root, None)
    # Level. Canvas stamps copied_from_outcome_id on course outcomes as well as
    # institutional ones, so it says nothing about level. An external_identifier or
    # the global flag marks an outcome imported from the institution's outcome bank;
    # failing that, the group and title are read for program or course wording.
    # Anything still undecided is "unknown" rather than guessed.
    group_titles = {g["id"]: g["title"] or "" for g in groups}
    program_words = re.compile(r"\b(program|plo|slo|degree|major|minor|ba|bs|b\.a\.|b\.s\.|ma|ms|phd|"
                               r"institution(al)?|university|core|gen(eral)?\s*ed|clat)\b|_(bs|ba|ms|ma)\b", re.I)
    course_words = re.compile(r"\b(clo|course|module|lesson|unit)\b|^clo\d", re.I)
    for o in outcomes:
        group = group_titles.get(o["group"], "")
        if o["external_identifier"] or o["is_global"]:
            o["level"], why = "program", "has an external identifier from the institution's outcome bank"
        elif course_words.search(o["title"] or "") or course_words.search(group):
            o["level"], why = "course", f'title or group "{group or o["title"]}" names a course outcome'
        elif program_words.search(o["title"] or "") or program_words.search(group):
            o["level"], why = "program", f'title or group "{group or o["title"]}" names a program outcome'
        else:
            o["level"], why = "unknown", "no external identifier and no program or course wording"
        o["level_source"] = "inferred: " + why
    return groups, outcomes


def read_modules(zf, resources):
    root = parse_xml(zf, "course_settings/module_meta.xml")
    out = []
    for m in ([] if root is None else root.findall("module")):
        items = []
        for it in m.iter("item"):
            ref = text(it, "identifierref")
            items.append({
                "id": it.get("identifier"), "title": text(it, "title"),
                "content_type": text(it, "content_type"), "ref": ref,
                "url": text(it, "url"), "indent": int(number(text(it, "indent")) or 0),
                "position": int(number(text(it, "position")) or 0) or None,
                "workflow_state": text(it, "workflow_state"),
            })
        title = text(m, "title") or ""
        week = re.search(r"\b(?:week|wk|module|unit)\s*0*(\d{1,2})\b", title, re.I)
        out.append({
            "id": m.get("identifier"), "title": title,
            "position": int(number(text(m, "position")) or 0) or None,
            "workflow_state": text(m, "workflow_state"),
            "unlock_at_utc": iso(utc(text(m, "unlock_at"))),
            "week": int(week.group(1)) if week else None,
            "items": items,
        })
    out.sort(key=lambda m: (m["position"] is None, m["position"] or 0))
    return out


# ---------------------------------------------------------------- main

def build_model(path, overrides=None):
    overrides = overrides or {}
    path = pathlib.Path(path)
    if not path.exists():
        raise ExportError(f"{path} does not exist")
    if not zipfile.is_zipfile(path):
        raise ExportError(f"{path} is not a zip file. A Canvas export (.imscc) is a zip; re-download it from "
                          "Canvas: Settings > Export Course Content > Course")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    warnings, unread = [], []
    with zipfile.ZipFile(path) as zf:
        names = set(zf.namelist())
        resources = read_manifest(zf)
        settings = parse_xml(zf, "course_settings/course_settings.xml")
        if settings is None:
            warnings.append("course_settings/course_settings.xml is missing: this looks like a plain Common "
                            "Cartridge rather than a Canvas export, so Canvas-only details are absent")
        start_at = utc(text(settings, "start_at"))
        conclude_at = utc(text(settings, "conclude_at"))

        # First pass: collect every date so the time zone can be inferred before
        # anything is converted to local time.
        raw_dates = []
        for n in names:
            if n.endswith(("assignment_settings.xml", "assessment_meta.xml")):
                x = parse_xml(zf, n)
                for tag in ("due_at", "unlock_at", "lock_at"):
                    for el in x.iter(tag):
                        when = utc((el.text or "").strip())
                        if when:
                            raw_dates.append(when)
        tz_fact = infer_time_zone(raw_dates, start_at, overrides)
        tz_name = tz_fact["value"]

        assignments, quizzes, discussions, pages, links, tools = [], [], [], [], [], []
        for n in sorted(names):
            if n.endswith("/assignment_settings.xml"):
                assignments.append(read_assignment(zf, n.split("/")[0], n, tz_name))
            elif n.endswith("/assessment_meta.xml"):
                quizzes.append(read_quiz(zf, n.split("/")[0], n, resources, tz_name))
        for ident, res in resources.items():
            rtype = res["type"] or ""
            if rtype == "webcontent" and (res["href"] or "").startswith("wiki_content/"):
                raw = read_html(zf, res["href"]) or ""
                meta = html_meta(raw)
                pages.append({"id": ident, "kind": "page", "title": meta.get("title"),
                              "slug": pathlib.PurePosixPath(res["href"]).stem, "href": res["href"],
                              "workflow_state": meta.get("workflow_state"),
                              "front_page": meta.get("front_page") == "true" or None,
                              "text": html_text(raw)})
            elif rtype.startswith("imsdt"):
                discussions.append(read_discussion(zf, ident, res, resources))
            elif rtype.startswith("imswl") and res["files"]:
                wl = parse_xml(zf, res["files"][0])
                url = wl.find("url") if wl is not None else None
                links.append({"id": ident, "kind": "web_link", "title": text(wl, "title"),
                              "url": url.get("href") if url is not None else None})
            elif rtype.startswith("imsbasiclti") and res["files"]:
                lti = parse_xml(zf, res["files"][0])
                tools.append({"id": ident, "kind": "external_tool", "title": text(lti, "title"),
                              "url": text(lti, "launch_url") or text(lti, "secure_launch_url")})
            elif rtype and not rtype.startswith(("webcontent", "associatedcontent", "imsqti", "imsdt", "imswl", "imsbasiclti")):
                unread.append(rtype)
        if unread:
            warnings.append(f"resource types not read: {sorted(set(unread))}")

        syllabus_raw = read_html(zf, "course_settings/syllabus.html")
        syllabus_text = html_text(syllabus_raw)
        rubrics = read_rubrics(zf)
        outcome_groups, outcomes = read_outcomes(zf)
        modules = read_modules(zf, resources)
        groups_root = parse_xml(zf, "course_settings/assignment_groups.xml")
        assignment_groups = [{"id": g.get("identifier"), "title": text(g, "title"),
                              "position": int(number(text(g, "position")) or 0) or None,
                              "weight": number(text(g, "group_weight"))}
                             for g in ([] if groups_root is None else groups_root.findall("assignmentGroup"))]
        files = sorted(n for n in names if n.startswith("web_resources/") and not n.endswith("/"))

    meetings_fact = infer_meetings(syllabus_text, overrides)

    # Term: Canvas's course dates are often padded well past the last class, so the
    # last day of teaching is taken as the latest of the dated work, not conclude_at.
    local_start = to_local(start_at, tz_name)
    due_locals = [to_local(utc(x["due_at_utc"]), tz_name) for x in assignments + quizzes if x["due_at_utc"]]
    first_day = local_start.date() if local_start else (min(due_locals).date() if due_locals else None)
    if overrides.get("term_end"):
        term_end = _fact(overrides["term_end"], "settings file", "set by the user", "high")
    elif due_locals:
        last = max(due_locals).date()
        conclude_local = to_local(conclude_at, tz_name)
        evidence = f"latest due date is {last.isoformat()}"
        if conclude_local and conclude_local.date() > last:
            evidence += f"; Canvas course end date {conclude_local.date().isoformat()} is later and was not used"
        term_end = _fact(last.isoformat(), "inferred from due dates", evidence, "medium")
    else:
        term_end = _fact(to_local(conclude_at, tz_name).date().isoformat() if conclude_at else None,
                         "course end date" if conclude_at else "none",
                         "no dated work; used the Canvas course end date" if conclude_at else "no dates at all", "low")
    last_day = dt.date.fromisoformat(term_end["value"]) if term_end["value"] else None
    sessions = meeting_dates(meetings_fact["value"], first_day, last_day)
    if overrides.get("cancelled"):
        cancelled = {d: "settings file" for d in overrides["cancelled"]}
    else:
        cancelled = find_cancellations(syllabus_raw, sessions)
    for s in sessions:
        s["cancelled"] = s["date"] in cancelled
        if s["cancelled"]:
            s["cancelled_evidence"] = cancelled[s["date"]]
    if sessions and not cancelled:
        warnings.append("no cancelled class meetings were found in the syllabus; holidays and breaks are "
                        "counted as class days unless the syllabus marks them with words such as 'No class'")

    for label, fact in (("time zone", tz_fact), ("meeting pattern", meetings_fact), ("term end", term_end)):
        if fact["value"] is None:
            warnings.append(f"{label} could not be inferred: {fact.get('reason') or fact['evidence']}. "
                            f"Checks that depend on it will be reported as not run.")
        elif fact["confidence"] != "high":
            warnings.append(f"{label} was inferred with {fact['confidence']} confidence: {fact['evidence']}")

    return {
        "schema_version": SCHEMA_VERSION,
        "source": {"file": path.name, "sha256": digest,
                   "read_at": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()},
        "course": {
            "title": text(settings, "title"), "code": text(settings, "course_code"),
            "start_at_utc": iso(start_at), "conclude_at_utc": iso(conclude_at),
            "default_view": text(settings, "default_view"),
            "group_weighting_scheme": text(settings, "group_weighting_scheme"),
        },
        "inferred": {"time_zone": tz_fact, "meetings": meetings_fact, "term_end": term_end,
                     "first_day": first_day.isoformat() if first_day else None},
        "sessions": sessions,
        "syllabus": {"text": syllabus_text},
        "modules": modules,
        "pages": sorted(pages, key=lambda p: p["href"] or ""),
        "assignments": assignments,
        "quizzes": quizzes,
        "discussions": discussions,
        "assignment_groups": assignment_groups,
        "rubrics": rubrics,
        "outcome_groups": outcome_groups,
        "outcomes": outcomes,
        "web_links": links,
        "external_tools": tools,
        "files": files,
        "warnings": warnings,
    }


def summary(model):
    inf = model["inferred"]
    lines = [f"Read {model['source']['file']}: {model['course']['title'] or '(untitled course)'}",
             f"  {len(model['modules'])} modules, {len(model['pages'])} pages, {len(model['assignments'])} assignments, "
             f"{len(model['quizzes'])} quizzes, {len(model['discussions'])} discussions, {len(model['rubrics'])} rubrics, "
             f"{len(model['outcomes'])} outcomes, {sum(not x['cancelled'] for x in model['sessions'])} class meetings "
             f"({sum(x['cancelled'] for x in model['sessions'])} cancelled)",
             "Assumptions:"]
    for label, key in (("Time zone", "time_zone"), ("Meetings", "meetings"), ("Last day of term", "term_end")):
        f = inf[key]
        value = f["value"]
        if isinstance(value, dict):
            value = f"{'/'.join(value['days'])} {value['start']}-{value['end']}"
        lines.append(f"  {label}: {value if value is not None else 'unknown'} "
                     f"({f['confidence']} confidence; {f['source']}; {f['evidence']})")
    if model["warnings"]:
        lines.append("Warnings:")
        lines += [f"  - {w}" for w in model["warnings"]]
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Read a Canvas course export into course_model.json")
    ap.add_argument("export", help="the .imscc file exported from Canvas")
    ap.add_argument("--out", default="course_model.json", help="where to write the model (default: course_model.json)")
    ap.add_argument("--settings", help="optional JSON file overriding inferred facts: time_zone, meetings, term_end")
    args = ap.parse_args(argv)
    overrides = {}
    if args.settings:
        try:
            overrides = json.loads(pathlib.Path(args.settings).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"error: could not read settings file {args.settings}: {exc}", file=sys.stderr)
            return 2
    try:
        model = build_model(args.export, overrides)
    except ExportError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    body = json.dumps(model, indent=2, ensure_ascii=False)
    pathlib.Path(args.out).write_text(body + "\n", encoding="utf-8")
    print(summary(model))
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
