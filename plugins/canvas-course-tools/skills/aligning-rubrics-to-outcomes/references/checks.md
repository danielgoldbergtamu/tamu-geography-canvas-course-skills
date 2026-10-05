# The checks

## Contents

- 1 Graded with no rubric
- 2 Rubric not used for grading
- 3 Rubric total and assignment points disagree
- 4 Rating levels hidden
- 5 Outcome criterion changes the score
- 6 Broken outcome link
- 7 Assignment measures no outcome
- 8 Outcome not measured
- 9 Rating levels have no descriptions
- 10 Course outcome rolls up to nothing

## 1 Graded with no rubric (defect)

An assignment worth points with no rubric. Students cannot see how it is graded, and no
outcome can be measured through it. Attendance items are skipped.

## 2 Rubric not used for grading (warning)

A rubric attached for reference only. Choosing a rating does not set the score, so the
grader enters it twice and the two can disagree.

## 3 Rubric total and assignment points disagree (defect, or warning for rounding)

The scored criteria do not add up to the assignment's points. Common when one rubric is
reused across assignments worth different amounts. Outcome criteria marked not to count
are left out of the total. A gap of 5 cents or less is reported as a warning: it comes
from rounding criterion points (three criteria at 16.67 make 50.01), and the fix is to give
the remainder to one criterion so top marks equal the assignment's points exactly.

## 4 Rating levels hidden (warning)

`free_form_criterion_comments` is on, so Canvas shows a comment box instead of the rating
levels, even when every level has a description.

## 5 Outcome criterion changes the score (warning)

A criterion linked to an outcome counts toward the score. Outcome criteria usually record
mastery on the outcome's own 4-point scale; counting them changes the assignment's
weighting.

## 6 Broken outcome link (defect)

A criterion links to an outcome the export does not contain.

## 7 Assignment measures no outcome (warning)

A graded assignment with a rubric, but no criterion linked to any outcome and no Canvas
alignment.

## 8 Outcome not measured (warning)

An outcome that no graded assignment measures. Reported for course and program outcomes.

## 9 Rating levels have no descriptions (note)

Every scored criterion in a rubric has rating levels with names and points but no
description of what earns them.

## 10 Course outcome rolls up to nothing (warning)

No graded assignment measures the course outcome together with any program outcome, so no
crosswalk row can be proposed. The instructor must say which program outcome it serves,
if any.

**Misses, for every check:** whether the rubric's criteria actually assess what the
outcome describes; New Quizzes; outcomes aligned at the account level but never imported
into the course.
