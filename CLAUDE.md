# Working rules for this repository

This file is for any Claude session editing this repository. It is not part of the
plugin and is not loaded when someone installs the skills.

## What this repository is

The public home of the Canvas course skills built in the GEOG 476 project
(`C:\Claude\476`, decision D-0021, request OR-125). The skills here hold the canonical
code. GEOG 476 uses released versions of them; it does not keep its own copies.

## Never let these in

This repository is public. Nothing from the GEOG 476 project may be copied into it:
no student names, email addresses, grades or submissions; no class recordings or
transcripts; no client project material; no third-party documents; no text from the
paper or the department report. Code is written fresh here, not copied, so its history
carries none of that. Test data is the synthetic sample course in `examples/` and
nothing else.

## Before every commit

1. Run `claude plugin validate . --strict` and `python3 tools/validate_skills.py`.
   Both must pass.
2. If anything a user would notice changed, bump `version` in
   `plugins/canvas-course-tools/.claude-plugin/plugin.json` and add a matching
   `CHANGELOG.md` entry. Users stay on the old version until the number changes.
3. Use American English and plain instructions: what the reader does, why, and how.

## Git on the mounted folder

The bridge cannot delete files, so git's lock files survive each command. Move any
`.git/*.lock` into `.git/stale-locks/` before running git. Dan pushes; sessions add and
commit only.
