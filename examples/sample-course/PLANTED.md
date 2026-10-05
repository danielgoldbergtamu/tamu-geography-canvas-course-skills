# SAMP 101 sample course

`sample-course.imscc` is a made-up Canvas course built by `build_sample_course.py`. It
contains no real people or real course material. Rebuild it with:

```
python3 examples/sample-course/build_sample_course.py
```

Every skill's tests run against it. This file lists what is in it, so a test can say
exactly what a skill should find. Change this file in the same commit as the builder.

## Facts the reader must infer

| # | Fact | Expected value | Planted to test |
|---|---|---|---|
| 1 | Time zone | `America/Chicago` | Deadlines on both sides of 1 November: 11:59 PM is 04:59 UTC before and 05:59 UTC after |
| 2 | Meeting days and times | Mon/Wed 10:00-11:15 | Office hours (Fri 2:00-3:00 PM) and a phone number in the syllabus must be ignored |
| 3 | Cancelled meetings | Mon 7 Sep 2026, Wed 25 Nov 2026 | A schedule table whose Monday and Wednesday columns say "No class"; the "Due Wednesday" column must not be read as a meeting column |
| 4 | Last day of term | 2026-12-09 | Canvas's course end date (15 January) is later and must not be used |
| 5 | Outcome levels | 2 program (external identifiers 9001, 9002), 3 course (CLO1-CLO3), 1 unknown ("Teamwork") | Level must not be guessed when there is no evidence |

## Defects planted for the other skills

| # | Defect | Where | Skill that should find it |
|---|---|---|---|
| 1 | Due before it is taught | Project Proposal is due Wed 9 Sep (week 3); the page that teaches it, Lecture 4, is in the Week 04 module | checking-course-sequence |
| 2 | Graded with nothing to submit | Participation 1: 5 points, submission type `none`, no rubric | checking-course-sequence, aligning-rubrics-to-outcomes |
| 3 | Graded assignment with no rubric | Lab 2: Projections | aligning-rubrics-to-outcomes |
| 4 | Rating levels hidden | The Lab rubric has `free_form_criterion_comments` true | aligning-rubrics-to-outcomes |
| 5 | Outcome never measured | CLO2 and Teamwork are linked to no rubric criterion | aligning-rubrics-to-outcomes |
| 6 | No Bloom's level is stated anywhere | Every page and assignment | tagging-bloom-levels |
| 7 | Image with no alt text | Lecture 3 page | fixing-canvas-accessibility |
| 8 | Skipped heading level (h2 then h4) | Lecture 3 page | fixing-canvas-accessibility |
| 9 | Link text that does not say where it goes ("click here") | Lecture 3 page | fixing-canvas-accessibility |
| 10 | Text that fails WCAG contrast (#bbbbbb on white) | Lecture 3 page | fixing-canvas-accessibility |
| 11 | Dated work left unpublished | Project Draft, Final Project | checking-course-sequence |
| 12 | Syllabus schedule disagrees with Canvas | The schedule lists Reading Response 1 under "Due Wednesday" in week 1 (26 Aug); Canvas has it due Sun 30 Aug | checking-course-sequence |
| 13 | Page text disagrees with Canvas | Lecture 4 says the Project Proposal is due September 16; Canvas has 9 September | checking-course-sequence |
| 14 | Image that is not in the export | Lecture 3 shows `projection.png`, which the export does not contain | checking-course-sequence, fixing-canvas-accessibility |
| 15 | Link into one specific Canvas course | The Welcome page links to `canvas.example.edu/courses/12345/...` | checking-course-sequence |

## Correct patterns that must NOT be reported

- The Reading Response rubric has an outcome criterion worth 0 points with
  `ignore_for_scoring` true. That is the right way to link a rubric to an outcome without
  changing its total.
- Instructor Notes is unpublished and in no module. It is not meant for students.
- Project Draft (11 Nov) and Final Project (9 Dec) are 28 days apart, more than the
  14-day revision gap.
- Reading Response 2 is listed under "Due Wednesday" in the week of 7 Sep and is due
  Wednesday 9 Sep. The schedule and Canvas agree.
