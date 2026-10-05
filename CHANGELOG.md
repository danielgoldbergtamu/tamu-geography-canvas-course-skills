# Changelog

Every release of the `canvas-course-tools` plugin is listed here, newest first. The
version number in `plugins/canvas-course-tools/.claude-plugin/plugin.json` must match the
newest entry. Claude Code keeps users on the version they installed until that number
changes, so a fix that does not bump the version does not reach anyone.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and version
numbers follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
