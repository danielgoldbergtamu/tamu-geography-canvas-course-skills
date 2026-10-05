# rubric_plan.json

The file `scripts/write_rubrics.py` reads. Every key is optional; a plan needs at least
one change. Identifiers come from `course_model.json` (`assignments[].id`,
`rubrics[].id`, `outcomes[].id`).

## Contents

- create
- add_outcomes
- show_rating_levels
- use_for_grading
- Example
- What the writer guarantees

## create

A new rubric, attached to an assignment and used for grading.

| Key | Required | Meaning |
|---|---|---|
| `assignment_id` | yes | The assignment to attach it to |
| `title` | no | Defaults to the assignment's title plus "rubric" |
| `criteria` | yes | Scored criteria. Their `points` must add up to the assignment's points |
| `criteria[].description` | yes | The criterion's name |
| `criteria[].long_description` | no | More detail shown to students |
| `criteria[].points` | yes | Equal to the highest rating's points |
| `criteria[].ratings` | yes | Highest first: `description`, `long_description` (what earns it), `points` |
| `outcomes` | no | Outcomes to add as criteria: identifier, external identifier or exact title |
| `replace_existing` | no | `true` to replace a rubric the assignment already has |

## add_outcomes

`[{"rubric_id": "...", "outcome": "..."}]` adds a criterion for the outcome to an existing
rubric. The criterion uses the outcome's own mastery scale and does not count toward the
score.

## show_rating_levels

`["<rubric id>", ...]` turns off free-form comments, so Canvas shows the rating levels.

## use_for_grading

`["<assignment id>", ...]` makes the attached rubric set the score when a rating is chosen.

## Example

```json
{
  "create": [
    {"assignment_id": "a04", "title": "Lab 2 rubric",
     "criteria": [
       {"description": "Correct projection chosen", "points": 10,
        "ratings": [
          {"description": "Full", "long_description": "Chooses a projection that preserves what the task measures and says why.", "points": 10},
          {"description": "Partial", "long_description": "Chooses a workable projection without a reason.", "points": 5},
          {"description": "None", "long_description": "No projection, or an unsuitable one.", "points": 0}]},
       {"description": "Distortion explained", "points": 10,
        "ratings": [
          {"description": "Full", "long_description": "Names the distortion and where it is largest.", "points": 10},
          {"description": "Partial", "long_description": "Mentions distortion without locating it.", "points": 5},
          {"description": "None", "long_description": "Does not discuss distortion.", "points": 0}]}],
     "outcomes": ["o-clo2"]}
  ],
  "add_outcomes": [{"rubric_id": "r01", "outcome": "9002"}],
  "show_rating_levels": ["r02"],
  "use_for_grading": []
}
```

## What the writer guarantees

- The original export is never modified; the output is a new file.
- Nothing is written unless the whole plan is valid.
- The XML is the same shape Canvas writes in its own exports: a course outcome is linked
  with `learning_outcome_identifierref`, an institutional outcome with
  `learning_outcome_external_identifier`, and an outcome criterion carries the outcome's
  mastery scale with `ignore_for_scoring` true.
- An attached rubric is set to be used for grading, with points and outcome results shown.

Not yet verified by a real Canvas import at the time of release: see the CHANGELOG.
