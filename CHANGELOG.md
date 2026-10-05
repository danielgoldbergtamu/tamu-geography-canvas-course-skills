# Changelog

Every release of the `canvas-course-tools` plugin is listed here, newest first. The
version number in `plugins/canvas-course-tools/.claude-plugin/plugin.json` must match the
newest entry. Claude Code keeps users on the version they installed until that number
changes, so a fix that does not bump the version does not reach anyone.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and version
numbers follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.0.1] - 2026-10-05

### Added

- Marketplace and plugin manifests.
- README, license, contributing guide and this changelog.
- `tools/validate_skills.py`, which checks every skill against the Agent Skills
  specification.
- A GitHub Actions workflow that runs both validators on every push.
