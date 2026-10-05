#!/usr/bin/env python3
"""Check every skill in this repository against the Agent Skills specification.

Run from the repository root:

    python3 tools/validate_skills.py

What it checks, for each plugins/*/skills/<folder>/SKILL.md:
  - the file starts with YAML frontmatter between two '---' lines;
  - `name` is 1-64 characters of lowercase letters, digits and single hyphens,
    does not start or end with a hyphen, contains neither "claude" nor "anthropic",
    and matches the folder name;
  - `description` is present and 1-1024 characters;
  - `compatibility`, if present, is 1-500 characters;
  - the body is under 500 lines, the limit in Anthropic's skill authoring guidance;
  - no backslash appears in a Markdown link target.

What it does NOT check: whether the description is any good, whether linked files
exist (claude plugin validate covers plugin paths, not links inside SKILL.md), or
whether scripts run. Those belong to tests and evaluations.

Standard library only, so it runs anywhere Python 3.10+ does.
Spec: https://agentskills.io/specification
"""
import pathlib
import re
import sys

NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
RESERVED = ("claude", "anthropic")
MAX_NAME = 64           # Agent Skills spec
MAX_DESCRIPTION = 1024  # Agent Skills spec
MAX_COMPATIBILITY = 500 # Agent Skills spec
MAX_BODY_LINES = 500    # Anthropic skill authoring best practices
LINK_RE = re.compile(r"\]\(([^)]+)\)")


def frontmatter(text):
    """Return (fields, body) from a SKILL.md, or raise ValueError."""
    if not text.startswith("---\n"):
        raise ValueError("does not start with a '---' frontmatter line")
    end = text.find("\n---", 4)
    if end == -1:
        raise ValueError("frontmatter has no closing '---' line")
    fields = {}
    key = None
    for line in text[4:end].splitlines():
        if not line.strip():
            continue
        if line[0] in " \t" and key:
            fields[key] = (fields[key] + " " + line.strip()).strip()
            continue
        if ":" not in line:
            raise ValueError(f"frontmatter line is not 'key: value': {line!r}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        if value in (">", "|", ">-", "|-"):
            value = ""
        fields[key] = value.strip('"').strip("'")
    return fields, text[end + 4:]


def check(skill_md):
    errors = []
    folder = skill_md.parent.name
    try:
        fields, body = frontmatter(skill_md.read_text(encoding="utf-8"))
    except ValueError as exc:
        return [str(exc)]
    name = fields.get("name", "")
    if not name:
        errors.append("missing `name`")
    else:
        if len(name) > MAX_NAME or not NAME_RE.match(name):
            errors.append(f"`name` {name!r} must be 1-{MAX_NAME} lowercase letters, digits and single hyphens")
        if any(word in name for word in RESERVED):
            errors.append(f"`name` {name!r} contains a reserved word")
        if name != folder:
            errors.append(f"`name` {name!r} does not match its folder {folder!r}")
    description = fields.get("description", "")
    if not description:
        errors.append("missing `description`")
    elif len(description) > MAX_DESCRIPTION:
        errors.append(f"`description` is {len(description)} characters; the limit is {MAX_DESCRIPTION}")
    if "compatibility" in fields and not 1 <= len(fields["compatibility"]) <= MAX_COMPATIBILITY:
        errors.append(f"`compatibility` must be 1-{MAX_COMPATIBILITY} characters")
    lines = body.count("\n")
    if lines >= MAX_BODY_LINES:
        errors.append(f"body is {lines} lines; keep it under {MAX_BODY_LINES} and move detail to references/")
    for target in LINK_RE.findall(body):
        if "\\" in target:
            errors.append(f"link target {target!r} uses a backslash; use forward slashes")
    return errors


def main():
    root = pathlib.Path(__file__).resolve().parent.parent
    skills = sorted(root.glob("plugins/*/skills/*/SKILL.md"))
    folders = sorted(p for p in root.glob("plugins/*/skills/*") if p.is_dir())
    failed = 0
    for folder in folders:
        if not (folder / "SKILL.md").exists():
            print(f"FAIL {folder.relative_to(root)}: folder has no SKILL.md")
            failed += 1
    for skill_md in skills:
        errors = check(skill_md)
        rel = skill_md.parent.relative_to(root)
        if errors:
            failed += 1
            for err in errors:
                print(f"FAIL {rel}: {err}")
        else:
            print(f"ok   {rel}")
    print(f"{len(skills)} skill(s) checked, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
