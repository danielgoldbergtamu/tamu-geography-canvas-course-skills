#!/usr/bin/env python3
"""Apply an accessibility fix plan to a copy of a Canvas export.

Usage:
    python3 fix_a11y.py COURSE.imscc a11y_plan.json                    # dry run
    python3 fix_a11y.py COURSE.imscc a11y_plan.json --apply            # write COURSE.accessible.imscc
    python3 fix_a11y.py COURSE.imscc a11y_plan.json --apply --skip-unfilled

Refuses a plan made from a different export (checked by SHA-256) and, unless
--skip-unfilled is given, a plan with any value still null. A value of "skip" leaves that
element unchanged. Each fix is applied only if its element's start tag is exactly as the
scan recorded it. The original export is never modified, and the same export and plan
always produce the same file. Standard library only.
"""
import argparse
import hashlib
import json
import pathlib
import sys
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import a11y_html as A  # noqa: E402


def main(argv=None):
    ap = argparse.ArgumentParser(description="Apply an accessibility fix plan to a copy of a Canvas export")
    ap.add_argument("export")
    ap.add_argument("plan")
    ap.add_argument("--apply", action="store_true", help="write the fixed copy (default: dry run)")
    ap.add_argument("--skip-unfilled", action="store_true", help="leave fixes whose value is still null")
    ap.add_argument("--out", help="default: COURSE.accessible.imscc beside the original")
    args = ap.parse_args(argv)
    src = pathlib.Path(args.export)
    try:
        plan = json.loads(pathlib.Path(args.plan).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: could not read the plan: {exc}", file=sys.stderr)
        return 2
    if hashlib.sha256(src.read_bytes()).hexdigest() != plan.get("sha256"):
        print("error: this plan was made from a different export. Run scan_a11y.py on this file first.", file=sys.stderr)
        return 2
    unfilled = [f for f in plan["fixes"] if f["value"] is None]
    if unfilled and not args.skip_unfilled:
        print(f"error: {len(unfilled)} fix(es) still need a value, for example {unfilled[0]['id']} "
              f"({unfilled[0]['rule']} on \"{unfilled[0]['title']}\": {unfilled[0]['needs']}). "
              "Fill them, set them to \"skip\", or pass --skip-unfilled.", file=sys.stderr)
        return 2
    todo = [f for f in plan["fixes"] if f["value"] not in (None, "skip")]
    by_file = {}
    for f in todo:
        by_file.setdefault(f["file"], []).append(f)
    with zipfile.ZipFile(src) as zf:
        infos = zf.infolist()
        files = {i.filename: zf.read(i.filename) for i in infos}
    changed = {}
    try:
        for name, fixes in by_file.items():
            changed[name] = A.apply(files[name].decode("utf-8"), fixes).encode("utf-8")
    except (ValueError, KeyError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(("Applying" if args.apply else "Dry run. Run again with --apply to make") +
          f" {len(todo)} fix(es) in {len(by_file)} file(s); {len(unfilled)} unfilled and "
          f"{sum(1 for f in plan['fixes'] if f['value'] == 'skip')} skipped:")
    kinds = {}
    for f in todo:
        kinds[f["rule"]] = kinds.get(f["rule"], 0) + 1
    for rule, n in sorted(kinds.items()):
        print(f"  {rule}: {n}")
    if not args.apply:
        return 0
    out = pathlib.Path(args.out) if args.out else src.with_name(src.stem + ".accessible.imscc")
    if out.resolve() == src.resolve():
        print("error: the output would overwrite the original export", file=sys.stderr)
        return 2
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for info in infos:
            new = zipfile.ZipInfo(info.filename, info.date_time)
            new.compress_type, new.external_attr = zipfile.ZIP_DEFLATED, info.external_attr
            zf.writestr(new, changed.get(info.filename, files[info.filename]))
    print(f"Wrote {out}. The original export was not changed. Rescan it with scan_a11y.py to confirm.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
