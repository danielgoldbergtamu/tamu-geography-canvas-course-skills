# Contributing

## Reporting a problem

Open an issue on GitHub. Say which skill you ran, what you expected, and what happened.
Do not attach your course export or paste student names, email addresses or grades into
an issue. If the problem only shows up with your course, describe the page or assignment
instead, or build a small made-up course that shows the same problem.

## Proposing a change

1. Fork the repository and make your change on a branch.
2. If you change a skill's behavior, add or update a test that shows the new behavior.
3. Run both validators before opening a pull request:

   ```
   claude plugin validate . --strict
   python3 tools/validate_skills.py
   ```

4. Add a line under `[Unreleased]` in `CHANGELOG.md` saying what changed and why.

## Rules every skill follows

- `SKILL.md` stays under 500 lines. Longer material goes in `references/`, linked
  directly from `SKILL.md`.
- The `name` is lowercase letters, numbers and single hyphens, and matches the folder.
- The `description` says what the skill does and when to use it, in the third person,
  in 1,024 characters or fewer.
- Paths use forward slashes.
- Every script lists its dependencies and fails with a message that says what to do.
- Every check says what it does not check. A partial check reported as complete is worse
  than no check.
- Each skill ships with at least three evaluations and runs against the sample course in
  `examples/`.
