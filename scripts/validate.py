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


TITLE_STOPWORDS = {"a", "an", "and", "for", "in", "of", "on", "the", "to", "with", "using"}


def title_words(title):
    """Content words of a course title, for comparing two titles by meaning.

    Stopwords and plural endings are dropped so that "Introduction to
    Algorithm" and "Introduction to Algorithms" compare equal, while
    "Fuzzy Systems" and "Game Theory" do not.
    """
    out = set()
    for w in re.split(r"[^a-z0-9]+", (title or "").lower()):
        if not w or w in TITLE_STOPWORDS:
            continue
        out.add(w[:-1] if len(w) > 3 and w.endswith("s") else w)
    return frozenset(out)


def title_overlap(a, b):
    """Jaccard similarity of two titles' content words, 0.0 to 1.0."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


# Below this, two titles sharing a course code describe different subjects
# rather than the same one worded differently.
DISTINCT_TITLE_THRESHOLD = 0.4

# Conflicts that predate this check and could not be settled against an
# official syllabus. They are reported as warnings so the rule can be enforced
# for everything else; resolving them needs the KTU 2019 scheme PDFs, which is
# tracked in issue #199. Nothing may be added here without a source: a new
# conflict is an error, and this list is expected to shrink to nothing.
UNRESOLVED_CODE_CONFLICTS = {
    ("a-p-j-abdul-kalam-technological-university", c)
    for c in ("est130", "mcn202", "cst203", "cst204", "cst205", "rlmca133", "pecht867")
}


# A course_title that swallowed the course code, e.g.
# "pccsl307-digital-systems-lab" instead of "digital-systems-lab".
TITLE_WITH_CODE = re.compile(r"^[a-z]{2,6}\d{3}[a-z]?-")
PLACEHOLDER_CODES = {"unknown", "na", "n/a", "none", "tbd", "todo", "xxx", ""}


def cross_file_checks(scope):
    """Checks that no single file can fail on its own.

    A file can be perfectly well-formed and still be wrong: the same course
    code carrying two different titles means one of them is misfiled, and
    nothing about either file in isolation reveals it. These run over the whole
    tree so that validating one file still catches a clash with an existing
    one, and report only findings that touch the files being validated.
    """
    findings = []
    everything = []
    for root, _dirs, names in os.walk("universities"):
        for n in names:
            if n.endswith(".md"):
                everything.append(os.path.join(root, n).replace(os.sep, "/"))

    by_code = {}
    for path in sorted(everything):
        m = PATH_RE.match(path)
        if not m:
            continue
        try:
            fm, err = parse_frontmatter(open(path, encoding="utf-8").read())
        except Exception:
            continue
        if err or not fm:
            continue
        code = (fm.get("course_code") or "").strip().lower()
        title = (fm.get("course_title") or "").strip().lower()

        if code in PLACEHOLDER_CODES:
            if path in scope:
                findings.append((path, True, f"course_code is a placeholder: '{code}'"))
            continue
        if TITLE_WITH_CODE.match(title):
            if path in scope:
                findings.append(
                    (path, True, f"course_title '{title}' begins with a course code; "
                                 "the code belongs in course_code alone")
                )
        by_code.setdefault((m.group(1), code), {}).setdefault(title_words(title), []).append(
            (path, title)
        )

    for (uni, code), variants in sorted(by_code.items()):
        if len(variants) < 2:
            continue
        touched = [p for entries in variants.values() for p, _ in entries if p in scope]
        if not touched:
            continue
        keys = list(variants)
        worst = min(
            title_overlap(a, b) for i, a in enumerate(keys) for b in keys[i + 1:]
        )
        spread = "; ".join(
            f"'{entries[0][1]}' in {len(entries)} file(s)"
            for entries in sorted(variants.values(), key=lambda e: -len(e))
        )
        # KTU publishes some shared courses under slightly different names per
        # branch, so differing titles alone are not proof of an error. Titles
        # with almost nothing in common are a different matter.
        distinct = worst < DISTINCT_TITLE_THRESHOLD
        if distinct and (uni, code) in UNRESOLVED_CODE_CONFLICTS:
            note = ("names two unrelated subjects, unresolved pending an "
                    "official source (see issue #199)")
            distinct = False
        elif distinct:
            note = "names two unrelated subjects"
        else:
            note = "names the same subject differently, which may be intentional"
        for path in sorted(touched):
            findings.append(
                (path, distinct,
                 f"course code '{code}' {note} across {uni}: {spread}")
            )
    return findings


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

    for path, fatal, msg in sorted(cross_file_checks({f.replace(os.sep, "/") for f in files})):
        if fatal:
            print(f"ERROR   {path}: {msg}")
            total_errors += 1
        else:
            print(f"warning {path}: {msg}")
            total_warnings += 1

    print(
        f"\nchecked {len(files)} file(s): {total_errors} error(s), {total_warnings} warning(s)"
    )
    sys.exit(1 if total_errors else 0)


if __name__ == "__main__":
    main()
