# How a Canvas export is laid out

Read this when the reader fails on an export, or when changing the reader. Everything
here was read off real Canvas exports, not from documentation alone: a specification
says what Canvas will accept, while an export shows what Canvas writes.

## Contents

- The zip
- Where each kind of item lives
- Dates
- Outcomes and rubrics
- Things that look like they mean something and do not

## The zip

A `.imscc` file is a zip. `imsmanifest.xml` at the root lists every resource with an
`identifier`, a `type` and its files. Canvas-only settings live in `course_settings/`.

| Resource `type` | What it is |
|---|---|
| `webcontent` with `href` under `wiki_content/` | A page |
| `webcontent` under `web_resources/` | An uploaded file |
| `associatedcontent/imscc_xmlv1p1/learning-application-resource` | An assignment folder, the syllabus, or a quiz's or discussion's Canvas settings |
| `imsqti_xmlv1p2/imscc_xmlv1p1/assessment` | A classic quiz |
| `imsdt_xmlv1p1` | A discussion or announcement |
| `imswl_xmlv1p1` | A web link |
| `imsbasiclti_xmlv1p3` | An external tool link |

## Where each kind of item lives

- **Assignment**: a folder named by its identifier holding `assignment_settings.xml` and
  one `.html` body.
- **Classic quiz**: a folder holding `assessment_meta.xml` (dates, points, settings) and
  `assessment_qti.xml` (questions); a copy of the questions is also in
  `non_cc_assessments/`.
- **Page**: `wiki_content/<slug>.html`. The title, identifier and `workflow_state` are
  `<meta>` tags in its `<head>`.
- **Modules**: `course_settings/module_meta.xml`. Each item's `identifierref` points at a
  resource identifier.
- **Rubrics**: `course_settings/rubrics.xml`. An assignment names its rubric in
  `rubric_identifierref`.
- **Outcomes**: `course_settings/learning_outcomes.xml`, as nested groups.
- **Syllabus**: `course_settings/syllabus.html`.
- **Course dates and settings**: `course_settings/course_settings.xml`.

## Dates

Canvas writes every date as UTC with no zone marker: `2026-09-11T04:59:00` is 11:59 PM
on 10 September in US Central daylight time. The course time zone is **not** in the export.
Daylight saving changes the offset partway through a fall or spring term, so a single
fixed offset is wrong for part of every term; convert with a real time-zone database.

`conclude_at` in `course_settings.xml` is the course's end date in Canvas, which is often
set weeks after the last class.

## Outcomes and rubrics

- A rubric criterion linked to a course outcome carries `learning_outcome_identifierref`
  (the outcome's identifier in `learning_outcomes.xml`). One linked to an institutional
  outcome carries `learning_outcome_external_identifier`. They are not interchangeable.
- An outcome criterion added to a rubric should have `ignore_for_scoring` true, or it
  changes the rubric's total.
- `free_form_criterion_comments` true makes Canvas show a comment box in place of the
  rating levels, even when every level has a description.

## Things that look like they mean something and do not

- `copied_from_outcome_id` is set on course outcomes copied between courses, not only on
  institutional ones.
- `is_global_outcome` was false on every outcome in the exports this was tested on,
  including institutional ones.
- A module's `workflow_state` and an item's `workflow_state` are separate: a published
  module can hold unpublished items.
