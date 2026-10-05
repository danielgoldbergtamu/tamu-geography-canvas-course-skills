---
name: tagging-bloom-levels
description: Proposes a revised Bloom's taxonomy level for every lecture, lab, activity, assignment, quiz and discussion in a Canvas course export, from the verbs its objectives and instructions use, links each assessed item to the course and program learning outcomes it measures, and checks that every outcome climbs through the term. Writes an editable levels file so the instructor can confirm or correct each level. Use when someone asks for the Bloom's levels of a course, wants to show scaffolding or progression across learning outcomes, or asks whether a course builds from lower-order to higher-order thinking.
license: MIT
---

# Tagging Bloom's levels

Proposes a Bloom's level for every learning item in a Canvas course, ties assessed items
to the outcomes they measure, and checks that each outcome climbs through the term.

**A proposed level is not a confirmed one.** Two careful verb-based proposers, built
separately and run on the same real course, agreed on the exact level for 35% of its
assignments. The instructor's confirmation is what turns a proposal into evidence, and this
skill is built around getting it.

## Run it

1. Run the tagger on the export (it runs the reader first when given an `.imscc`):

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/tagging-bloom-levels/scripts/tag_bloom.py" "COURSE.imscc" --out-dir bloom
   ```

   Where `${CLAUDE_PLUGIN_ROOT}` is not filled in, use `scripts/tag_bloom.py` inside this
   skill's folder. The reading-canvas-exports skill must be installed beside this one.

2. Read `bloom/bloom_report.md`. Then review the items a person must decide: every row in
   `bloom/bloom_levels.csv` whose confidence is `none` or `low`, and whose type is not
   `page`. For each one:
   - read its text in `bloom/course_model.json` (find it by `id`);
   - decide the level the item asks students to work at, using the definitions in
     [references/levels.md](references/levels.md);
   - write that level in the `note` column as `Claude proposes <Level>: <one-line reason>`.
     **Never write in `confirmed_level`.** That column is the instructor's.

3. Report to the user, in this order:
   - how many items have a proposed level, how many are unknown, and how many are
     confirmed;
   - each outcome's progression, one line each, saying which climb and which do not;
   - the warnings;
   - the items you reviewed in step 2, as a numbered list with your proposed level and
     reason, so the user can answer "1 yes, 2 Analyze, 3 yes".

4. When the user confirms or corrects levels, write them into `confirmed_level` in
   `bloom_levels.csv`, then rerun with the file so the progression uses them:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/skills/tagging-bloom-levels/scripts/tag_bloom.py" "COURSE.imscc" --out-dir bloom --levels bloom/bloom_levels.csv
   ```

## How a level is proposed

- **High confidence:** a verb opens a line in a learning-objectives section ("By the end of
  this lecture you will be able to: Explain…").
- **Medium:** a verb opens an instruction line elsewhere in the item.
- **Low:** only the title opens with a verb.
- **Unknown:** no line opens with a listed verb. Nothing is guessed.
- The highest level found wins, because work that analyzes in order to judge is judging.
- Only the bare verb counts, so a heading such as "Named reviewers" is not read as "name".
- Verbs that published lists place at different levels (compare, check, select, write,
  build, map and others) are not used. The full table and the reasons are in
  `assets/bloom_verbs.json`.
- Attendance items get no level: they record presence, not a learning task.

## How outcomes are linked and checked

An assignment, quiz or discussion measures an outcome when its rubric has a criterion
linked to that outcome, or Canvas records an alignment between them. For each outcome, its
items are put in due-date order and the outcome is checked:

- **Climbs:** it reaches more than one level and ends at or above where it starts. Dips
  along the way are normal.
- **Does not climb:** every item is at the same level.
- **Ends lower than it starts.**
- **Measured once,** or **not measured** by any item.

Details: [references/levels.md](references/levels.md).
