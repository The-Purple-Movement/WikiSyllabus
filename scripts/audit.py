#!/usr/bin/env python3
"""Cross-file data audit for the WikiSyllabus commons.

`validate.py` checks each file on its own: path shape, required frontmatter,
field consistency. It does that correctly, and it is not what this script
replaces. Every defect found during the KTU 2024 correction series was
individually valid and only visible when files were compared against each
other:

  - `pccst402` appeared twice in one semester while three courses were absent
  - `pccsl305` and `oecs301` name courses that exist in no official document
  - `uchut346` carried an older scheme's syllabus in some branches, not others
  - two files ended a module mid-word at "cost-benefit analysis, capit"
  - `gaest305`, a four-credit core course, had no file at all

Those are the five classes this script looks for. See issue #214.

Usage:
    python3 scripts/audit.py                # audit the whole tree
    python3 scripts/audit.py --markdown     # report for a CI job summary
    python3 scripts/audit.py --root PATH    # audit a different tree (tests)

Exit code 0 = no errors. 1 = errors found. Warnings and info never fail.
No external dependencies.

A note on tooling, because it cost real time to learn: BSD grep on macOS
treats files containing non-ASCII bytes as binary under a C locale and
silently reports nothing, and large local scans of this tree time out. Every
check here reads through Python and is immune to both. Audit in CI, not by
hand.
"""
import argparse
import os
import re
import statistics
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from validate import PATH_RE, parse_frontmatter  # noqa: E402

ERROR, WARNING, INFO = "error", "warning", "info"

# A sentence that ends deliberately ends with one of these. Used only to
# compare a section against itself, never as a house style rule.
TERMINAL = tuple(".!?:;)]\"'’”*_`")

# Below this, a module heading has a title and essentially no syllabus. Kept
# deliberately low. A terse one-line module is a real module, and an earlier
# threshold of 60 flagged 405 of them; only a placeholder should trip this.
THIN_MODULE_CHARS = 25

# Two files sharing a course code should describe the same course. Word-set
# overlap, not character diff: robust to reordering and reformatting.
DRIFT_THRESHOLD = 0.75

# A semester this far below the median for the same semester across branches
# is more likely missing a course than genuinely smaller.
COVERAGE_SLACK = 2

MODULE_HEADING = re.compile(r"^#{2,4}\s*Module\b", re.I)
HEADING = re.compile(r"^#{1,6}\s")

# Citation lists punctuate by their own rules: some entries end in a year, some
# in a publisher, some in an edition. Judging them against a prose habit
# produced nothing but false positives, so the truncation rule skips them.
CITATION_HEADING = re.compile(
    r"\b(references?|text\s*books?|textbooks?|reference\s*books?|bibliography|"
    r"further\s+reading|video\s+links?|web\s+resources?|online\s+resources?|"
    r"resources|links)\b", re.I)


def body_of(text):
    """The document below the frontmatter block."""
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return stripped
    end = stripped.find("\n---", 3)
    return stripped[end + 4:] if end != -1 else stripped


def sections(body):
    """Split a body into (heading, [content lines]) pairs.

    Content excludes blank lines, headings and horizontal rules, so a section
    is judged on its prose alone.
    """
    out, heading, lines = [], "(preamble)", []
    for raw in body.split("\n"):
        line = raw.rstrip()
        if HEADING.match(line):
            out.append((heading, lines))
            heading, lines = line.strip("# ").strip(), []
        elif line.strip() and line.strip() != "---":
            lines.append(line.strip())
    out.append((heading, lines))
    return [(h, ls) for h, ls in out if ls]


def truncated_sections(body):
    """Sections whose last line breaks the section's own punctuation habit.

    The giveaway in the real case was not the missing full stop, since plenty
    of bullet lists have none. It was that every other line in that module
    ended with one and the last did not, because the sentence was cut off
    mid-word. Judging each section against itself is what keeps this quiet on
    the thousand-odd files that simply never punctuate.
    """
    found = []
    for heading, lines in sections(body):
        if CITATION_HEADING.search(heading):
            continue                      # citations have no prose habit
        if len(lines) < 3:
            continue                      # too few lines to establish a habit
        closed = [ln for ln in lines if ln.endswith(TERMINAL)]
        if len(closed) / len(lines) < 0.7:
            continue                      # this section does not punctuate
        if not lines[-1].endswith(TERMINAL):
            found.append((heading, lines[-1]))
    return found


def thin_modules(body):
    """Module headings carrying almost no syllabus."""
    found = []
    for heading, lines in sections(body):
        if not MODULE_HEADING.match("## " + heading):
            continue
        if len(" ".join(lines)) < THIN_MODULE_CHARS:
            found.append(heading)
    return found


def unsafe_bytes(raw):
    """Bytes that make this file unreadable or hazardous to downstream tools."""
    if b"\x00" in raw:
        return "contains NUL bytes"
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        return f"is not valid UTF-8 ({exc.reason} at byte {exc.start})"
    bad = {ch for ch in text if ord(ch) < 32 and ch not in "\t\n\r"}
    if bad:
        names = ", ".join(sorted(f"U+{ord(ch):04X}" for ch in bad))
        return f"contains control characters ({names})"
    return None


def similarity(a, b):
    """Jaccard overlap of the two word sets, 0.0 to 1.0."""
    wa = set(re.findall(r"[a-z0-9]+", a.lower()))
    wb = set(re.findall(r"[a-z0-9]+", b.lower()))
    if not wa or not wb:
        return 1.0 if wa == wb else 0.0
    return len(wa & wb) / len(wa | wb)


def collect(root):
    """Parse every course file under root into a record."""
    records, findings = [], []
    for dirpath, _dirs, names in os.walk(root):
        for name in sorted(names):
            if not name.endswith(".md"):
                continue
            path = os.path.join(dirpath, name)
            rel = os.path.relpath(path).replace(os.sep, "/")
            match = PATH_RE.match(rel)
            if not match:
                continue                  # pyq, overview, misfiled: validate.py's job
            try:
                raw = open(path, "rb").read()
            except OSError as exc:
                findings.append((ERROR, rel, f"unreadable: {exc}"))
                continue
            reason = unsafe_bytes(raw)
            if reason:
                findings.append((ERROR, rel, reason))
                continue
            text = raw.decode("utf-8")
            frontmatter, err = parse_frontmatter(text)
            if err:
                continue                  # validate.py already reports this
            records.append({
                "path": rel,
                "university": match.group(1),
                "branch": match.group(2),
                "year": match.group(3),
                "semester": match.group(4),
                "code": (frontmatter.get("course_code") or "").lower(),
                "title": (frontmatter.get("course_title") or "").lower(),
                "body": body_of(text),
            })
    return records, findings


def check_duplicate_codes(records):
    """Two files in one semester claiming the same course code."""
    groups = defaultdict(list)
    for r in records:
        if r["code"]:
            key = (r["university"], r["branch"], r["year"], r["semester"])
            groups[(key, r["code"])].append(r["path"])
    out = []
    for (_key, code), paths in sorted(groups.items()):
        if len(paths) > 1:
            others = ", ".join(sorted(paths)[1:])
            out.append((ERROR, sorted(paths)[0],
                        f"course code '{code}' is claimed by {len(paths)} files "
                        f"in this semester; the generated data will carry a "
                        f"duplicate and hide a course. Also: {others}"))
    return out


def by_code(records):
    """Group by university, year and course code, across branches."""
    groups = defaultdict(list)
    for r in records:
        if r["code"]:
            groups[(r["university"], r["year"], r["code"])].append(r)
    return groups


def check_title_conflicts(records):
    """One course code naming two different subjects."""
    out = []
    for (_uni, year, code), rs in sorted(by_code(records).items()):
        titles = sorted({r["title"] for r in rs if r["title"]})
        if len(titles) > 1:
            where = ", ".join(sorted(r["path"] for r in rs))
            out.append((ERROR, sorted(r["path"] for r in rs)[0],
                        f"course code '{code}' ({year}) names {len(titles)} "
                        f"different subjects: {'; '.join(titles)}. Files: {where}"))
    return out


def check_body_drift(records):
    """Same course code and title, materially different syllabus."""
    out = []
    for (_uni, year, code), rs in sorted(by_code(records).items()):
        if len(rs) < 2:
            continue
        if len({r["title"] for r in rs if r["title"]}) > 1:
            continue                      # already an error above
        rs = sorted(rs, key=lambda r: r["path"])
        base = rs[0]
        drifted = [r for r in rs[1:]
                   if similarity(base["body"], r["body"]) < DRIFT_THRESHOLD]
        if drifted:
            where = ", ".join(r["path"] for r in drifted)
            out.append((WARNING, base["path"],
                        f"course code '{code}' ({year}) is shared across branches "
                        f"but the syllabus text differs materially from: {where}. "
                        f"One of them may be from an older scheme"))
    return out


def check_truncation_and_thinness(records):
    out = []
    for r in sorted(records, key=lambda r: r["path"]):
        for heading, last in truncated_sections(r["body"]):
            out.append((WARNING, r["path"],
                        f"section '{heading}' may be truncated: every other line "
                        f"ends a sentence, this one does not: ...{last[-48:]!r}"))
        for heading in thin_modules(r["body"]):
            out.append((WARNING, r["path"],
                        f"module '{heading}' has a heading but almost no syllabus"))
    return out


def check_coverage_outliers(records):
    """A semester holding far fewer courses than its peers in other branches.

    The only signal available for a course that is missing entirely: there is
    no list of what each branch ought to contain, so the branches are compared
    against each other.
    """
    counts = defaultdict(int)
    for r in records:
        counts[(r["university"], r["year"], r["semester"], r["branch"])] += 1

    peers = defaultdict(dict)
    for (uni, year, sem, branch), n in counts.items():
        peers[(uni, year, sem)][branch] = n

    out = []
    for (uni, year, sem), branches in sorted(peers.items()):
        if len(branches) < 3:
            continue                      # too few peers to call anything odd
        median = statistics.median(branches.values())
        for branch, n in sorted(branches.items()):
            if n <= median - COVERAGE_SLACK:
                out.append((INFO, f"universities/{uni}/{branch}/{year}/{sem}/",
                            f"holds {n} course(s) where the median across "
                            f"{len(branches)} branches is {median:g}; a course "
                            f"may be missing"))
    return out


CHECKS = [
    ("duplicate course codes", check_duplicate_codes),
    ("course codes naming two subjects", check_title_conflicts),
    ("cross-branch syllabus drift", check_body_drift),
    ("truncated or thin sections", check_truncation_and_thinness),
    ("semesters below their peers", check_coverage_outliers),
]


def run(root):
    records, findings = collect(root)
    grouped = [("unreadable or unsafe files", findings)]
    for name, fn in CHECKS:
        grouped.append((name, fn(records)))
    return records, grouped


def report_text(records, grouped):
    total = {ERROR: 0, WARNING: 0, INFO: 0}
    for _name, findings in grouped:
        for level, path, message in findings:
            total[level] += 1
            label = "ERROR  " if level == ERROR else f"{level} "
            print(f"{label} {path}: {message}")
    print(f"\naudited {len(records)} course file(s): "
          f"{total[ERROR]} error(s), {total[WARNING]} warning(s), "
          f"{total[INFO]} info")
    return total[ERROR]


def report_markdown(records, grouped):
    errors = sum(1 for _n, fs in grouped for f in fs if f[0] == ERROR)
    warnings = sum(1 for _n, fs in grouped for f in fs if f[0] == WARNING)
    infos = sum(1 for _n, fs in grouped for f in fs if f[0] == INFO)
    print("## WikiSyllabus data audit\n")
    print(f"Audited **{len(records)}** course files: "
          f"**{errors}** errors, **{warnings}** warnings, **{infos}** info.\n")
    for name, findings in grouped:
        if not findings:
            continue
        print(f"### {name} ({len(findings)})\n")
        for level, path, message in findings[:50]:
            print(f"- **{level}** `{path}`: {message}")
        if len(findings) > 50:
            print(f"- ...and {len(findings) - 50} more")
        print()
    if not any(fs for _n, fs in grouped):
        print("No findings.")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="universities")
    parser.add_argument("--markdown", action="store_true",
                        help="emit a report for a CI job summary")
    args = parser.parse_args()

    if not os.path.isdir(args.root):
        print(f"no such directory: {args.root}", file=sys.stderr)
        return 2

    records, grouped = run(args.root)
    errors = (report_markdown if args.markdown else report_text)(records, grouped)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
