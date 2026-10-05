---
name: aligning-rubrics-to-outcomes
description: Audits and repairs the chain from rubric to assignment to course learning outcome to program learning outcome in a Canvas course export. Finds graded assignments with no rubric, rubric totals that disagree with assignment points, hidden rating levels, outcome criteria that change scores, outcomes nothing measures, and course outcomes that roll up to no program outcome; proposes a course-to-program crosswalk; drafts missing rubrics from assignment instructions; and writes reviewed rubrics and outcome links into a new copy of the export for import. Use when someone asks whether their rubrics are attached and aligned, wants rubrics generated, or needs to show how assignments map to course and program outcomes.
license: MIT
---

# Aligning rubrics to outcomes

Checks every link in the chain **rubric → assignment → course outcome → program outcome**,
drafts what is missing for the instructor to review, and writes the reviewed changes into
a new copy of the export. The original export is never changed.

## Step 1: Audit

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/aligning-rubrics-to-outcomes/scripts/audit_alignment.py" "COURSE.imscc" --out-dir alignment
```

Where `${CLAUDE_PLUGIN_ROOT}` is not filled in, use `scripts/audit_alignment.py` inside this
skill's folder. The reading-canvas-exports skill must be installed beside this one.

Report to the user from `alignment/alignment_report.md`, in this order: how each outcome's
level (course or program) was decided; the defects; the warnings; and the proposed
crosswalk, saying plainly that every crosswalk row is a proposal.

## Step 2: Draft a plan (only if the user wants changes)

Write `alignment/rubric_plan.json` in the format in
[references/rubric-plan.md](references/rubric-plan.md). For each change:

- **A missing rubric:** read the assignment's instructions in `course_model.json`. Write
  two to five criteria for what the instructions actually ask for, each with three to
  five rating levels whose descriptions say what earns them. The criteria's points must
  add up to the assignment's points. Add outcome criteria only for outcomes the
  instructions clearly serve.
- **An outcome nothing measures:** propose which existing rubric should carry a criterion
  for it, and say why.
- **Hidden rating levels, or a rubric not used for grading:** list the fix.

Show the user the plan as a numbered list, with each drafted rubric in full, and wait for
their answer. Change the plan as they say. Do not apply anything they have not approved.

## Step 3: Dry run, then apply

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/aligning-rubrics-to-outcomes/scripts/write_rubrics.py" "COURSE.imscc" alignment/rubric_plan.json
python3 "${CLAUDE_PLUGIN_ROOT}/skills/aligning-rubrics-to-outcomes/scripts/write_rubrics.py" "COURSE.imscc" alignment/rubric_plan.json --apply
```

The first command lists every change and writes nothing. The second writes
`COURSE.rubrics.imscc` beside the original. The writer refuses a plan whose points do not
add up, or that names an assignment, rubric or outcome the export does not have.

## Step 4: Check the result

Run step 1 again on `COURSE.rubrics.imscc` and confirm that the findings the plan
targeted are gone and nothing new appeared. Then tell the user where the new file is and
how to import it: in Canvas, **Settings → Import Course Content → Canvas Course Export
Package**, choosing the new file. Recommend importing into a sandbox course first.

## Confirming the crosswalk

Canvas has no field that links a course outcome to a program outcome, so the crosswalk is
inferred: a course outcome is proposed to serve a program outcome when an assignment
measures both. Expect extra rows when a capstone assignment measures many outcomes at
once, and missing rows when a designed roll-up has no assignment measuring both. Tested
on one real course, it recovered four of five designed roll-ups, missed the one with no
shared assignment, and proposed four extra links through the capstone. When the user confirms or rejects rows, write `yes` or `no` in the
`confirmed` column of `outcome_crosswalk.csv` and rerun step 1 with
`--crosswalk alignment/outcome_crosswalk.csv`.

What each check looks for and misses: [references/checks.md](references/checks.md).
