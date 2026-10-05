---
name: checking-course-sequence
description: Checks the order and dates of a Canvas course from its export and builds a graph of weeks, class meetings, modules, pages, assignments, quizzes and discussions. Finds work due before the week that teaches it, dates in the syllabus or pages that disagree with Canvas, dead links, graded work with nothing to grade, items students cannot find, short draft-to-final gaps, and deadlines students cannot see yet. Use when someone asks whether a course is in the right order, whether anything is due before it is taught, whether syllabus dates match Canvas, or wants a week-by-week view of a Canvas course.
license: MIT
---

# Checking a course's sequence

Reads a Canvas export, checks that the course happens in an order a student can follow,
and builds a graph of how its parts connect.

## Run it

1. Find the `.imscc` file. If the user already has a `course_model.json` from the
   reading-canvas-exports skill, use that instead.
2. Run the checker. Given an `.imscc`, it runs the reader first:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/checking-course-sequence/scripts/check_sequence.py" "COURSE.imscc" --out-dir sequence
   ```

   Where `${CLAUDE_PLUGIN_ROOT}` is not filled in, use `scripts/check_sequence.py` inside
   this skill's folder. The reading-canvas-exports skill must be installed beside this one
   to read an `.imscc` directly. Python 3.10 or later; nothing else.

3. Open `sequence/sequence_report.md` and report to the user, in this order:
   - the assumptions it lists (time zone, meetings, cancelled classes, the date deadlines
     are counted from), each with its confidence;
   - the count of defects, warnings and notes;
   - every **defect**, with its evidence, in the report's order;
   - the warnings, grouped by check;
   - one line on the notes.
4. Tell the user where the three files are: `sequence_report.md` to read,
   `sequence_findings.json` for tools, and `course_graph.json`, the graph.
5. Do not change the course. This skill reports; fixing is the user's decision.

If the user says the export is from an earlier date, rerun with `--as-of YYYY-MM-DD`
so "due soon" is counted from the right day.

## What it checks

| # | Check | Severity |
|---|---|---|
| 1 | A date in the syllabus or a page disagrees with the item's Canvas due date | Defect |
| 2 | A link to a page, assignment, quiz, discussion or file the export does not contain | Defect |
| 3 | An item is due before the first class of the week its module covers | Defect |
| 4 | An assignment is worth points with nothing to submit and no rubric | Defect (a note when the title says it is attendance) |
| 5 | A published item is in no module | Warning |
| 6 | An item is due more than a week after the week its module covers | Warning |
| 7 | A draft and its final are fewer than 14 days apart | Warning |
| 8 | An item is due on a day class was cancelled | Note |
| 9 | Dated work is unpublished: a warning if due within 7 days, otherwise one summary note | Warning or note |
| 10 | A link points into one particular Canvas course by its web address | Warning |

A check whose inputs could not be inferred (for example, no meeting pattern in the
syllabus) is reported as **not run**, with the reason, and every other check still runs.

What each check looks at, why it exists, and what it misses:
[references/checks.md](references/checks.md). The graph's format:
[references/graph.md](references/graph.md).
