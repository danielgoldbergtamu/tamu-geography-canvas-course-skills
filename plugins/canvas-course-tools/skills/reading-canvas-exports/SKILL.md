---
name: reading-canvas-exports
description: Reads a Canvas course export (.imscc) into one course_model.json file that lists the course's modules, pages, assignments, quizzes, discussions, rubrics, learning outcomes and dated class meetings, and infers the facts Canvas does not export (time zone, meeting days and times, cancelled classes, last day of term) with the evidence for each. Use first whenever someone provides a Canvas export or .imscc file, asks what is in a Canvas course, or runs any other skill in this plugin; the other skills read its output.
license: MIT
---

# Reading a Canvas export

Turns one Canvas course export into `course_model.json`. Every other skill in this
plugin reads that file, so run this first.

## Run it

1. Find the `.imscc` file the user provided. If there is more than one, ask which course.
2. Run the reader, writing the model next to the export:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/reading-canvas-exports/scripts/read_export.py" "COURSE.imscc" --out course_model.json
   ```

   In Claude Code, `${CLAUDE_PLUGIN_ROOT}` is filled in for you. Where it is not (for
   example in the Claude app), use `scripts/read_export.py` inside this skill's folder.
   The script needs Python 3.10 or later and nothing else.

3. Read what the script printed and report it to the user in this order:
   - the course title and the counts of each kind of item;
   - **Assumptions**: the time zone, meeting days and times, cancelled meetings and last
     day of term, each with its confidence and the evidence it was read from;
   - **Warnings**, word for word.

4. Do not stop to ask the user for anything the script inferred. If a fact is inferred
   with low confidence or could not be inferred, say so plainly and say which checks in
   the other skills will be reported as not run because of it.

## When an inference is wrong

The user can correct any inferred fact with a small settings file and run the reader
again. Only write this file if the user says an inference is wrong:

```json
{
  "time_zone": "America/Chicago",
  "meetings": {"days": ["Tue", "Thu"], "start": "12:45", "end": "14:00"},
  "term_end": "2026-12-08",
  "cancelled": ["2026-11-24", "2026-11-26"]
}
```

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/reading-canvas-exports/scripts/read_export.py" "COURSE.imscc" --out course_model.json --settings course_settings.json
```

Every key is optional. A key that is present replaces the inferred value entirely.

## What the reader infers, and how

| Fact | Where it comes from |
|---|---|
| Time zone | Canvas stores every date in UTC. The reader tries common time zones and picks the one that puts the most deadlines on round local times (11:59 PM, on the hour), with daylight saving applied |
| Meeting days and times | A line in the syllabus with days and a time range, such as "T/Th 12:45PM - 2:00PM". Lines about office hours, review sessions and exams are ignored |
| Cancelled meetings | Rows of a schedule table, or lines, in the syllabus that say "No class", "holiday", "Thanksgiving", "spring break" and similar, with a date |
| Last day of term | The latest due date. Canvas's course end date is often weeks later and is not used |
| Program or course level of each outcome | An external identifier from the institution's outcome bank means program level; otherwise the group and title wording decides; otherwise "unknown" |

## What it does not read

- Student data of any kind. Exports do not contain submissions or grades.
- Calendar events, which Canvas does not include in a course export.
- Quiz questions beyond counting them.
- New Quizzes, which Canvas exports separately.

Full field-by-field details: [references/course-model.md](references/course-model.md).
How a Canvas export is laid out: [references/canvas-export-format.md](references/canvas-export-format.md).
