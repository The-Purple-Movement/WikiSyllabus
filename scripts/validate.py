#!/usr/bin/env python3
"""Validate WikiSyllabus files: structure and frontmatter.

Usage:
    python3 scripts/validate.py                      # validate the whole tree
    python3 scripts/validate.py path/to/file.md ...  # validate specific files (CI uses this)

Exit code 0 = all valid. 1 = errors found (warnings alone do not fail).
No external dependencies.
"""
import os
import re
import sys

REQUIRED_FIELDS = [
    "country",
    "university",
    "branch",
    "version",
    "semester",
    "course_code",
    "course_title",
    "language",
    "contributor",
]

# universities/<university>/<branch>/<year>/<semester>/<file>.md
PATH_RE = re.compile(
    r"^universities/([a-z0-9-]+)/([a-z0-9-]+)/(\d{4})/(s\d{2})/([a-z0-9_-]+)\.md$"
)

# Accepted short codes: frontmatter may use the alias while the folder uses
# the canonical slug. Extend this map when a new university has an
# established short name.
UNIVERSITY_ALIASES = {
    "a-p-j-abdul-kalam-technological-university": {"ktu"},
    "kerala-technical-university": {"ktu"},
    "massachusetts-institute-of-technology": {"mit"},
    "cochin-university-of-science-and-technology": {"cusat"},
    "mulearn-foundation": {"mulearn"},
    "national-institute-of-technology-calicut": {"nitc"},
    "indian-institute-of-space-science-and-technology": {"iist"},
}


def parse_frontmatter(text):
    """Minimal YAML frontmatter parser: returns (dict, error_string)."""
    if not text.lstrip().startswith("---"):
        return None, "missing YAML frontmatter block"
    stripped = text.lstrip()
    end = stripped.find("\n---", 3)
    if end == -1:
        return None, "frontmatter opened with --- but never closed"
    block = stripped[3:end]
    data = {}
    for line in block.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        data[key.strip()] = value.strip().strip("\"'")
    return data, None


def validate_file(path):
    errors, warnings = [], []
    rel = os.path.relpath(path).replace(os.sep, "/")

    m = PATH_RE.match(rel)
    if not m:
        errors.append(
            "path does not match universities/<university>/<branch>/<year>/<sNN>/<file>.md"
        )
        return errors, warnings

    uni, branch, year, semester = m.group(1), m.group(2), m.group(3), m.group(4)

    try:
        text = open(path, encoding="utf-8").read()
    except Exception as exc:
        return [f"unreadable: {exc}"], warnings

    fm, err = parse_frontmatter(text)
    if err:
        errors.append(err)
        return errors, warnings

    for field in REQUIRED_FIELDS:
        if field not in fm or not fm[field]:
            errors.append(f"frontmatter missing required field: {field}")

    if fm.get("university"):
        declared = fm["university"].lower()
        accepted = {uni} | UNIVERSITY_ALIASES.get(uni, set())
        if declared not in accepted:
            errors.append(
                f"frontmatter university '{fm['university']}' does not match folder '{uni}'"
            )
    if fm.get("branch") and fm["branch"] != branch:
        warnings.append(
            f"frontmatter branch '{fm['branch']}' does not match folder '{branch}'"
        )
    if fm.get("version") and fm["version"] != year:
        warnings.append(
            f"frontmatter version '{fm['version']}' does not match folder year '{year}'"
        )
    if fm.get("semester"):
        try:
            sem_num = int(fm["semester"])
            if sem_num != int(semester[1:]):
                warnings.append(
                    f"frontmatter semester '{fm['semester']}' does not match folder '{semester}'"
                )
        except ValueError:
            errors.append(f"semester must be a number, got '{fm['semester']}'")

    if fm.get("contributor") and not fm["contributor"].startswith("@"):
        warnings.append("contributor should be a GitHub handle starting with @")

    body = text.lstrip()
    body = body[body.find("\n---") + 4:] if body.startswith("---") else body
    if len(body.strip()) < 100:
        warnings.append("file body looks near-empty; add objectives/modules/references")

    return errors, warnings


def main():
    args = sys.argv[1:]
    if args:
        files = [a for a in args if a.endswith(".md") and a.startswith("universities/")]
    else:
        files = []
        for root, _dirs, names in os.walk("universities"):
            for n in names:
                if n.endswith(".md"):
                    files.append(os.path.join(root, n))

    total_errors = 0
    total_warnings = 0
    for f in sorted(files):
        errors, warnings = validate_file(f)
        for e in errors:
            print(f"ERROR   {f}: {e}")
        for w in warnings:
            print(f"warning {f}: {w}")
        total_errors += len(errors)
        total_warnings += len(warnings)

    print(
        f"\nchecked {len(files)} file(s): {total_errors} error(s), {total_warnings} warning(s)"
    )
    sys.exit(1 if total_errors else 0)


if __name__ == "__main__":
    main()
