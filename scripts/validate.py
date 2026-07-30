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

# Previous-year question papers:
# universities/<university>/<branch>/<year>/<semester>/pyq/<subjectid>-<examyear>[-<session>].md
PYQ_PATH_RE = re.compile(
    r"^universities/([a-z0-9-]+)/([a-z0-9-]+)/(\d{4})/(s\d{2})/pyq/([a-z0-9_]+)-(\d{4})(?:-([a-z]+))?\.md$"
)

PYQ_REQUIRED_FIELDS = ["course_code", "exam_year", "contributor"]

# Programme documentation: universities/<university>/<branch>/<year>/overview.md
# Describes a whole degree (structure, requirements, progression) rather than
# one course, so it carries prose instead of course frontmatter. A separate
# file type with its own rules, not an exemption from the course rules.
OVERVIEW_PATH_RE = re.compile(
    r"^universities/([a-z0-9-]+)/([a-z0-9-]+)/(\d{4})/overview\.md$"
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
    "university-of-oxford": {"oxford"},
    "iisc-bengaluru": {"iisc"},
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


def validate_pyq(path, rel, match):
    """Validate a previous-year-question paper file."""
    errors, warnings = [], []
    exam_year = match.group(6)
    try:
        text = open(path, encoding="utf-8").read()
    except Exception as exc:
        return [f"unreadable: {exc}"], warnings

    fm, err = parse_frontmatter(text)
    if err:
        errors.append(err)
        return errors, warnings

    for field in PYQ_REQUIRED_FIELDS:
        if field not in fm or not fm[field]:
            errors.append(f"frontmatter missing required field: {field}")

    if fm.get("exam_year") and fm["exam_year"] != exam_year:
        errors.append(
            f"frontmatter exam_year '{fm['exam_year']}' does not match filename year '{exam_year}'"
        )

    if fm.get("contributor") and not fm["contributor"].startswith("@"):
        warnings.append("contributor should be a GitHub handle starting with @")

    body = text.lstrip()
    body = body[body.find("\n---") + 4:] if body.startswith("---") else body
    if len(body.strip()) < 80:
        warnings.append("paper body looks near-empty; add the actual questions")

    return errors, warnings


def validate_overview(path):
    """Programme documentation: prose, not course frontmatter."""
    errors, warnings = [], []
    try:
        text = open(path, encoding="utf-8").read()
    except Exception as exc:
        return [f"unreadable: {exc}"], warnings

    body = text.strip()
    if body.startswith("---"):
        errors.append(
            "overview.md is prose, not a course file; drop the frontmatter "
            "or move this content into a course file under <sNN>/"
        )
    if not body.startswith("#"):
        errors.append("overview.md should open with a heading naming the programme")
    if len(body) < 200:
        warnings.append(
            "overview looks thin; describe the degree structure and progression"
        )
    return errors, warnings


def shadowed_frontmatter(text):
    """True when a second, complete frontmatter block follows the first.

    A repair in this repository once prepended a generated block onto files
    whose own frontmatter was merely missing its opening delimiter. The result
    parses as valid (the parser stops at the first block) while the real
    metadata sits below it, unread, and the contributor loses attribution.

    The test is deliberately strict, because `---` is also a Markdown
    horizontal rule and over a thousand files use one. A block qualifies only
    if it carries every required field exactly once and nothing else, which
    ordinary prose and rules do not.
    """
    if not text.lstrip().startswith("---"):
        return False
    stripped = text.lstrip()
    first_end = stripped.find("\n---", 3)
    if first_end == -1:
        return False

    after = stripped[first_end + 4:]
    if after[:1] not in ("\n", ""):        # the delimiter must end its own line
        return False
    candidate_start = after.lstrip("\n")   # blank lines between blocks are allowed
    second_end = candidate_start.find("\n---")
    if second_end == -1:
        return False
    block = candidate_start[:second_end]

    # A fence opening before the candidate means we are inside a code example.
    if (after[: len(after) - len(candidate_start)] + block).count("```") % 2:
        return False
    if "```" in block:
        return False

    seen = []
    for line in block.split("\n"):
        if not line.strip():
            return False                   # frontmatter blocks have no blank lines
        m = re.match(r"^([a-z_]+):\s*\S", line)
        if not m:
            return False                   # prose, indentation or a bare word
        seen.append(m.group(1))
    return sorted(seen) == sorted(REQUIRED_FIELDS)


def validate_file(path):
    errors, warnings = [], []
    rel = os.path.relpath(path).replace(os.sep, "/")

    if OVERVIEW_PATH_RE.match(rel):
        return validate_overview(path)
    if os.path.basename(rel) == "overview.md":
        errors.append(
            "overview.md belongs at universities/<university>/<branch>/<year>/overview.md"
        )
        return errors, warnings

    pyq = PYQ_PATH_RE.match(rel)
    if pyq:
        return validate_pyq(path, rel, pyq)

    if "/pyq/" in rel:
        errors.append(
            "pyq path must match universities/<u>/<b>/<year>/<sNN>/pyq/<subjectid>-<examyear>[-<session>].md"
        )
        return errors, warnings

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

    if shadowed_frontmatter(text):
        errors.append(
            "a second complete frontmatter block follows the first; the block "
            "below is unread and its contributor loses attribution. Keep one "
            "block, and check git history before discarding either"
        )

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
