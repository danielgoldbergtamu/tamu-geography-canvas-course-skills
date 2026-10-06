---
name: fixing-canvas-accessibility
description: Scans every HTML page in a Canvas course export (.imscc) for WCAG 2.1 AA accessibility problems, writes a fix plan, and applies it to a new copy of the export ready to import. Finds images without alt text, skipped or empty headings, link text such as "click here", text that fails color contrast, data tables without headers, scope or captions, and embedded content without titles. Fixes with one right answer are automatic; alt text and link text are drafted for a person to approve. Use when someone asks to check or fix the accessibility of a Canvas course, prepare a course for ADA Title II or WCAG compliance, or clean up a course before a review.
license: MIT
---

# Fixing accessibility in a Canvas export

Scan, plan, fix, repackage, verify. The original export is never changed; the fixed
course is a new `.imscc` beside it.

## Step 1: Scan

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/fixing-canvas-accessibility/scripts/scan_a11y.py" "COURSE.imscc" --out-dir a11y
```

Where `${CLAUDE_PLUGIN_ROOT}` is not filled in, use `scripts/scan_a11y.py` inside this
skill's folder. Python 3.10 or later; nothing else.

Report to the user from `a11y/a11y_report.md`: the totals, the table by rule, the pages
with the most findings, and the **Not checked** section in full. Files such as PDFs are
outside what this scan reads, and the user must hear that.

## Step 2: Complete the plan

`a11y/a11y_plan.json` holds one entry per fixable finding:

- `auto`: one right answer (a skipped heading level, a header cell's scope, a color made
  just dark enough to pass). Leave these as they are.
- `proposed`: prefilled (a table caption from the nearest heading, an embed title from
  its site, "first_row" for a table's header). Read each and improve it if it is wrong.
- `needs_value`: alt text and link text, which only someone who knows the content can
  write. For each:
  - **Alt text:** open the image from the export (its `src` is in the entry's `element`,
    under `web_resources/`), look at it, and write what it shows in one sentence, or `""`
    if it is purely decorative.
  - **Link text:** read the sentence around the link and write text that names where it
    goes, such as "EPSG projection registry", not the address itself.

Any value may be set to `"skip"` to leave that element alone.

Show the user every `proposed` and `needs_value` entry you filled, as a numbered list with
the page, what you wrote and why, and wait for their answer. Change the plan as they say.

## Step 3: Dry run, then apply

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/fixing-canvas-accessibility/scripts/fix_a11y.py" "COURSE.imscc" a11y/a11y_plan.json
python3 "${CLAUDE_PLUGIN_ROOT}/skills/fixing-canvas-accessibility/scripts/fix_a11y.py" "COURSE.imscc" a11y/a11y_plan.json --apply
```

The fixer refuses a plan made from a different export, a plan with an empty value (unless
`--skip-unfilled`), and any fix whose element no longer looks exactly as the scan saw it.
It writes `COURSE.accessible.imscc` and changes only the elements the plan names.

## Step 4: Verify and hand over

Rescan the new file with step 1 and report what is left. Then tell the user where the file
is and how to import it: in Canvas, **Settings → Import Course Content → Canvas Course
Export Package**. Recommend a sandbox course first. Importing replaces pages with the same
identity, so any page edited by hand in Canvas since the export was taken will be
overwritten; say so.

Rules, their WCAG criteria and how each fix works: [references/rules.md](references/rules.md).
