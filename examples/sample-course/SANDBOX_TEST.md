# Testing the rubric writer in a sandbox Canvas course

`sample-course.rubrics.imscc` is the made-up SAMP 101 course after `rubric_plan.json`
was applied by `aligning-rubrics-to-outcomes/scripts/write_rubrics.py`. Importing it is
the check that Canvas accepts what the writer produces. Use a blank sandbox course, never
a course with students.

## Import it

1. In Canvas, open a blank sandbox course.
2. Go to **Settings**, then **Import Course Content**.
3. For **Content Type**, choose **Canvas Course Export Package**.
4. Choose `sample-course.rubrics.imscc`, select **All content**, and click **Import**.
5. Wait for the import to say **Completed**. If it says **Partially Completed**, open the
   issues list and copy each message.

## Check these five things

| # | Where | What you should see |
|---|---|---|
| 1 | Assignments, then **Lab 2: Projections** | A rubric named **Lab 2 rubric** with two criteria, "Correct projection chosen" and "Distortion explained", each worth 10 points, plus a criterion for **CLO2: Choose a projection** |
| 2 | The same rubric | The CLO2 criterion is marked as not counting toward the score, and the rubric total reads 20 |
| 3 | Assignments, then **Lab 1: Coordinate Systems** | The **Lab** rubric shows its rating levels (Full, Partial, None), not a comment box |
| 4 | Assignments, then **Reading Response 1** | The **Reading Response** rubric now has a criterion for **PLO-METHOD: Applies spatial methods** |
| 5 | **Outcomes** | CLO2 and PLO-METHOD each show at least one alignment |

Report the result as an issue on the repository, or tell the person who sent you this.
If all five pass, the writer's output is accepted by Canvas.
