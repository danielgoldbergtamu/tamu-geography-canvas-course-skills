# Changelog

Every release of the `canvas-course-tools` plugin is listed here, newest first. The
version number in `plugins/canvas-course-tools/.claude-plugin/plugin.json` must match the
newest entry. Claude Code keeps users on the version they installed until that number
changes, so a fix that does not bump the version does not reach anyone.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and version
numbers follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.3.1] - 2026-10-05

### Fixed

- `checking-course-sequence` counted "due soon" from the UTC date the export was read.
  In the evening in the Americas that is already tomorrow, so deadlines were counted
  from the wrong day. It now uses the date in the course's own time zone.
- `aligning-rubrics-to-outcomes`: the rubric writer keeps each entry's timestamp, so
  the same export and plan always produce the same file.

### Added

- `examples/sample-course/SANDBOX_TEST.md`, `rubric_plan.json` and
  `sample-course.rubrics.imscc`: a file and five checks for verifying the rubric writer
  by importing into a blank sandbox Canvas course.

## [0.3.0] - 2026-10-05

### Added

- `aligning-rubrics-to-outcomes` skill. `audit_alignment.py` runs ten checks on the chain
  from rubric to assignment to course outcome to program outcome: graded work with no
  rubric, rubrics not used for grading, rubric totals that disagree with assignment
  points (rounding gaps of a few cents are warnings), hidden rating levels, outcome
  criteria that change the score, broken outcome links, assignments and outcomes that
  measure or are measured by nothing, and course outcomes that roll up to nothing. It
  proposes a course-to-program crosswalk from assignments that measure both, with a
  `confirmed` column for the instructor.
- `write_rubrics.py` writes a reviewed plan (new rubrics, outcome criteria, rating levels
  shown, rubrics used for grading) into a new copy of the export, in the XML shape Canvas
  writes in its own exports. Dry run by default; refuses a plan whose points do not add
  up or that names anything the export lacks; never modifies the original.

### Known limits

- Files written by `write_rubrics.py` have been checked by re-reading and re-auditing
  them, but not yet by importing one into Canvas. Import into a sandbox course first.
- Tested on one real course, the inferred crosswalk recovered four of five designed
  roll-ups, missed one that no assignment measures, and proposed four extra links
  through capstone assignments that measure several outcomes at once.

## [0.2.0] - 2026-10-05

### Added

- `tagging-bloom-levels` skill. Proposes a revised Bloom's taxonomy level for every
  lecture, lab, activity, assignment, quiz and discussion from the verbs its objectives
  and instructions open with, with high, medium or low confidence and the line it was
  read from. Items with no listed verb are reported as unknown, never guessed; Claude
  then reads each one and proposes a level with a reason for the instructor to confirm.
  Links assessed items to course and program outcomes through rubric criteria and Canvas
  alignments, and checks that every outcome climbs. Writes `bloom_levels.csv` with a
  `confirmed_level` column; rerun with `--levels` to use the instructor's levels.
- `assets/bloom_verbs.json`: the verb table, with seventeen verbs excluded because
  published lists disagree on their level, each with its reason.

### Changed

- `reading-canvas-exports`: table cells in page text are separated by a tab, so an
  objective in one cell no longer runs into the outcome code in the next.
- The sample course has learning objectives and instructions with known levels: one
  outcome that does not climb, one that climbs, and six items with no usable verb.

### Known limits

- On a real course, this skill and an independently built verb-based tagger agreed on the
  exact level for 35% of assignments. Proposed levels are a starting point for the
  instructor, not a measurement.

## [0.1.0] - 2026-10-05

The first release meant for other people to use.

### Added

- `checking-course-sequence` skill. Runs ten checks on a Canvas export and writes a
  report with the assumptions it made, a week-by-week timeline and numbered findings, plus
  a findings file and a graph of weeks, meetings, modules and items
  (`course_graph.json`). Checks: dates in the syllabus or pages that disagree with Canvas;
  dead internal links; work due before the week that teaches it; graded work with nothing
  to grade; published items in no module; module week and due week out of step; drafts
  and finals fewer than 14 days apart; deadlines on cancelled class days; unpublished work
  due soon; links into one specific Canvas course. Tested on a real course export, where
  it found two final assignments whose syllabus dates had not followed a deadline change.

### Changed

- `reading-canvas-exports`: `course_model.json` is now format 1.1. Every item and the
  syllabus carry `links` (each link and embedded image or video, classified), and the
  syllabus carries `tables`. Format 1.0 files still read the same; the sequence checker
  asks for 1.1.
- The sample course now plants four more cases: a syllabus date and a page date that
  disagree with Canvas, an image missing from the export, and a link into one Canvas
  course.

## [0.0.2] - 2026-10-05

### Added

- `reading-canvas-exports` skill. Reads a Canvas export into `course_model.json` and
  infers what Canvas does not export: the time zone (from deadlines, with daylight
  saving), meeting days and times (from the syllabus, ignoring office hours), cancelled
  meetings (from "No class" rows in the syllabus schedule), the last day of term, and
  whether each outcome is program or course level. Every inference records its evidence
  and confidence. Standard library only, and works on Windows without a time-zone
  database.
- `examples/sample-course/`: a made-up course, SAMP 101, with known facts and planted
  defects listed in `PLANTED.md`, rebuilt byte-for-byte by its builder.
- 19 tests, run in CI, covering each inference in both directions.

## [0.0.1] - 2026-10-05

### Added

- Marketplace and plugin manifests.
- README, license, contributing guide and this changelog.
- `tools/validate_skills.py`, which checks every skill against the Agent Skills
  specification.
- A GitHub Actions workflow that runs both validators on every push.
