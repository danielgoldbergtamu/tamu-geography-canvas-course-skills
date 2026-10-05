# course_graph.json

Nodes and edges describing how a course fits together. Written by
`scripts/check_sequence.py` next to the report.

## Nodes

Every node has `id`, `type` and `label`.

| type | id | Extra fields |
|---|---|---|
| `week` | `week:<n>` | |
| `meeting` | `meeting:<YYYY-MM-DD>` | `date`, `cancelled` |
| `module` | `module:<id>` | `position` |
| `page`, `assignment`, `quiz`, `discussion`, `announcement` | `item:<id>` | `published`, and `due_local` when dated |

## Edges

| type | from → to | Meaning |
|---|---|---|
| `has_meeting` | week → meeting | The meeting falls in that week of the term |
| `covers_week` | module → week | The module's title names that week |
| `contains` | module → item | The module lists the item |
| `due_in_week` | item → week | The item's due date falls in that week |
| `links_to` | item → item | The item's body links to the other item |

Week 1 is the calendar week (Monday to Sunday) containing the course's first day.

## Using it

Load it into any graph tool. For example, items that are `due_in_week` a week earlier
than the week their module `covers_week` are the items check 3 reports. Pages with no
incoming `contains` or `links_to` edge are unreachable.
