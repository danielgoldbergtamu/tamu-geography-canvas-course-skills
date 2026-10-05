# Changelog

Every release of the `canvas-course-tools` plugin is listed here, newest first. The
version number in `plugins/canvas-course-tools/.claude-plugin/plugin.json` must match the
newest entry. Claude Code keeps users on the version they installed until that number
changes, so a fix that does not bump the version does not reach anyone.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and version
numbers follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

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
