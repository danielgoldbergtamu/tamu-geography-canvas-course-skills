# course_model.json

The file `scripts/read_export.py` writes. Every other skill in this plugin reads it.
`schema_version` is `1.0`; a change that removes or renames a field raises the major
number.

## Contents

- Top level
- inferred
- sessions
- Items: pages, assignments, quizzes, discussions
- modules
- rubrics
- outcomes and outcome_groups
- Conventions

## Top level

| Field | Type | Meaning |
|---|---|---|
| `schema_version` | string | Version of this format |
| `source` | object | `file`, `sha256` of the export, and `read_at` (UTC) |
| `course` | object | `title`, `code`, `start_at_utc`, `conclude_at_utc`, `default_view`, `group_weighting_scheme` |
| `inferred` | object | Facts Canvas does not export. See below |
| `sessions` | array | Every scheduled class meeting, including cancelled ones |
| `syllabus` | object | `text`: the syllabus as plain text |
| `modules` | array | Modules in course order, each with its items |
| `pages`, `assignments`, `quizzes`, `discussions` | arrays | Course content. See below |
| `assignment_groups` | array | `id`, `title`, `position`, `weight` |
| `rubrics` | array | See below |
| `outcome_groups`, `outcomes` | arrays | See below |
| `web_links`, `external_tools` | arrays | `id`, `title`, `url` |
| `files` | array | Paths of uploaded files inside the export |
| `warnings` | array of strings | Everything the reader could not do or was unsure of |

## inferred

Each of `time_zone`, `meetings` and `term_end` is a fact object:

| Field | Meaning |
|---|---|
| `value` | The inferred value, or `null` if it could not be inferred |
| `source` | Where it came from: `inferred from due dates`, `inferred from the syllabus`, `settings file`, or `none` |
| `evidence` | The exact text or numbers it was read from |
| `confidence` | `high`, `medium` or `low` |
| `reason` | Present only when `value` is null: why |

- `time_zone.value` is an IANA name such as `America/Chicago`.
- `meetings.value` is `{"days": ["Tue", "Thu"], "start": "12:45", "end": "14:00"}`, in local
  24-hour time.
- `term_end.value` is a local date, `YYYY-MM-DD`.
- `first_day` is the local date the course starts.

A skill that needs a fact whose value is null reports the checks that depend on it as
**not run**, with the reason, and runs everything else.

## sessions

One entry per scheduled meeting from `first_day` to `term_end` on the meeting days:
`date`, `weekday`, `week` (1 for the first week of the term), `start`, `end`,
`cancelled`, and `cancelled_evidence` when cancelled. Cancelled meetings stay in the list
so a report can say a deadline falls on a day with no class.

## Items

Every item has `id` (the Canvas identifier, which module items and rubrics refer to),
`kind`, `title` and `text` (the body as plain text). Then:

- **pages**: `slug`, `href` (path inside the export), `workflow_state`, `front_page`.
- **assignments**: `due_at_utc`, `due_local`, `unlock_at_utc`, `lock_at_utc`,
  `points_possible`, `grading_type`, `submission_types` (a list; `none` and `on_paper` mean
  nothing is uploaded), `assignment_group`, `workflow_state`, `rubric` (a rubric `id` or
  null), `rubric_used_for_grading`, `peer_reviews`, `peer_review_count`,
  `omit_from_final_grade`, `position`, `href`.
- **quizzes**: `quiz_type`, the same date fields, `points_possible`, `assignment_group`,
  `workflow_state`, `question_count`.
- **discussions**: `kind` is `discussion` or `announcement`; `workflow_state`; `assignment`
  (the graded assignment's title, if graded). Read from the Common Cartridge
  specification; not yet tested against a real export containing discussions.

`workflow_state` is Canvas's own word: `active` or `published` means students can see it,
`unpublished` means they cannot.

## modules

In course order: `id`, `title`, `position`, `workflow_state`, `unlock_at_utc`, `week`
(a number when the title names a week, unit or module number, otherwise null), and
`items`. Each item has `title`, `content_type` (`WikiPage`, `Assignment`, `Quizzes::Quiz`,
`DiscussionTopic`, `ExternalUrl`, `ContextExternalTool`, `ContextModuleSubHeader`,
`Attachment`), `ref` (the `id` of the page, assignment or other item), `url`, `indent`,
`position` and `workflow_state`.

## rubrics

`id`, `title`, `points_possible`, `free_form_criterion_comments` (true means Canvas shows a
comment box instead of the rating levels), and `criteria`. Each criterion has `id`,
`description`, `long_description`, `points`, `mastery_points`, `ignore_for_scoring`,
`outcome` (an outcome `id` when the criterion is linked to a course outcome),
`outcome_external_id` (when linked to an institutional outcome), and `ratings`
(`description`, `points`, `long_description`).

## outcomes and outcome_groups

Groups: `id`, `title`, `parent`, `source_outcome_group_id`.
Outcomes: `id`, `title`, `description`, `group`, `external_identifier`,
`copied_from_outcome_id`, `is_global`, `mastery_points`, `points_possible`, `alignments`
(Canvas's own record of what the outcome is aligned to: `content_type` and `content_id`),
`level` (`program`, `course` or `unknown`) and `level_source` (why).

`copied_from_outcome_id` does not mean an outcome is institutional: Canvas sets it on
course outcomes copied between courses too.

## Conventions

- Dates ending `_utc` are UTC ISO 8601. Dates ending `_local` carry the inferred zone's
  offset. Canvas itself writes UTC with no offset; the reader adds it.
- Text fields are plain text with one line per paragraph, list item or table row.
- Nothing is ever dropped silently: anything the reader skipped is named in `warnings`.
