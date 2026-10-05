# The checks

Every check below was written after the defect it looks for reached students in a real
course. Each one says what it does not catch, because a partial check reported as
complete is worse than no check.

## Contents

- 1 Date drift
- 2 Dead links
- 3 Due before taught
- 4 Graded with nothing to grade
- 5 Not in any module
- 6 Module week and due week disagree
- 7 Draft-to-final gap
- 8 Due on a cancelled class day
- 9 Dated work unpublished
- 10 Links into a specific Canvas course

## 1 Date drift

**Looks at:** syllabus tables with a column headed "Due" (with a weekday, as in "Due
Thursday", or holding a date), and any sentence in the syllabus or a page that names an
item, contains the word "due" and gives a date. Each written date is compared with the
item's Canvas due date in the course's time zone.

**Why:** a due date that lives in two places drifts. Moving a deadline in Canvas does not
change the syllabus, and the syllabus is the document students rely on.

**Misses:** dates written without the word "due"; relative dates ("next Tuesday"); a
sentence naming two items, which is skipped because it cannot say which date is whose;
dates inside images or attached files.

## 2 Dead links

**Looks at:** every link and image in the syllabus, pages, assignments, quizzes and
discussions that points inside the course: pages (by identifier or URL name),
assignments, quizzes, discussions and uploaded files.

**Misses:** links to the web, which need a network to check; links inside uploaded files.

## 3 Due before taught

**Looks at:** each dated assignment and quiz placed in a module whose title names a week
("Week 4", "Week 04 — Projections"). If it is due before the first class meeting of that
week, it is due before the material it sits beside is taught.

**Misses:** courses whose modules are named by unit or topic rather than week (the check
reports not run); whether the page actually teaches what the assignment asks for. Module
placement is the evidence of when something is taught.

## 4 Graded with nothing to grade

**Looks at:** assignments worth points whose submission type is none and which have no
rubric. Neither a student nor a grader can see what earns the points. Titles that say
attendance, roll call or check-in are reported as a note, since those are usually graded
from a roll.

**Misses:** assignments graded from something outside Canvas that has a rubric.

## 5 Not in any module

**Looks at:** published pages, assignments, quizzes and discussions that no module lists.
In a course whose home page is Modules, these are hard to find. Says whether another page
links to the item. Attendance items and the front page are skipped.

**Misses:** courses that are navigated another way on purpose; items hidden by the
course's navigation settings.

## 6 Module week and due week disagree

**Looks at:** an item due more than one week after the week its module covers. Usually a
deadline that was extended without moving the item, or a module filed in the wrong week.

## 7 Draft-to-final gap

**Looks at:** pairs whose titles differ only by draft, rough, final, revised or a number.
Fewer than 14 days between the two leaves little time to grade the draft and revise.
Fourteen days is the gap one course settled on after seven days left four to grade and
three to revise; treat it as a starting point.

**Misses:** pairs named differently ("Proposal" and "Report").

## 8 Due on a cancelled class day

**Looks at:** deadlines on a meeting the syllabus cancels. Not necessarily wrong; worth
knowing.

## 9 Dated work unpublished

**Looks at:** dated items students cannot see in the export. Counted from the day the
export was read, or `--as-of`: overdue or due within 7 days is a warning; the rest is one
note, since many courses open one week at a time.

**Misses:** anything published in Canvas after the export was taken. The export is a
snapshot.

## 10 Links into a specific Canvas course

**Looks at:** web links of the form `https://<school>/courses/<number>/...`. They keep
pointing at that course after this one is copied to a new term.
