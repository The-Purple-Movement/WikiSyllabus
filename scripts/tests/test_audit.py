#!/usr/bin/env python3
"""Regression tests for the cross-file data audit.

Every positive case below is a defect that actually shipped, reduced to the
smallest tree that reproduces it. The negative cases matter more: the audit
runs over 1700 files, so a check that cries wolf is worse than no check, and
most of what follows exists to prove each rule stays quiet on ordinary data.

Run:  python3 scripts/tests/test_audit.py
"""
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import audit  # noqa: E402

U = "a-p-j-abdul-kalam-technological-university"

CASES = []


def case(name, check, expected):
    """Register a case: build a tree, run one check, count findings."""
    def wrap(fn):
        CASES.append((name, check, expected, fn))
        return fn
    return wrap


def doc(code, title, body, branch="computer-science", semester=3):
    return (f'---\ncountry: "india"\nuniversity: "ktu"\nbranch: "{branch}"\n'
            f'version: "2024"\nsemester: {semester}\ncourse_code: "{code}"\n'
            f'course_title: "{title}"\nlanguage: "english"\n'
            f'contributor: "@someone"\n---\n\n# {code.upper()}: {title}\n\n{body}\n')


def tree(files):
    """Write {relative path: text} under a temp root, return the root."""
    root = tempfile.mkdtemp()
    for rel, text in files.items():
        path = os.path.join(root, "universities", rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        mode = "wb" if isinstance(text, bytes) else "w"
        with open(path, mode) as fh:
            fh.write(text)
    return root


# --------------------------------------------------------------------------
# 1. Duplicate course codes. The pccst402 defect, which reached production.
# --------------------------------------------------------------------------

@case("two files in one semester claim the same code", "duplicate", 1)
def _():
    return tree({
        f"{U}/computer-science/2024/s04/02.md": doc("pccst402", "dbms", "Body."),
        f"{U}/computer-science/2024/s04/03.md": doc("pccst402", "dbms", "Body."),
    })


@case("the same code in two different semesters is fine", "duplicate", 0)
def _():
    return tree({
        f"{U}/computer-science/2024/s03/01.md": doc("uchut346", "econ", "B.", semester=3),
        f"{U}/computer-science/2024/s04/01.md": doc("uchut346", "econ", "B.", semester=4),
    })


@case("a common course shared across branches is fine", "duplicate", 0)
def _():
    return tree({
        f"{U}/computer-science/2024/s03/01.md": doc("uchut346", "econ", "B."),
        f"{U}/chemical-engineering/2024/s03/01.md":
            doc("uchut346", "econ", "B.", branch="chemical-engineering"),
    })


# --------------------------------------------------------------------------
# 2. One code, two subjects. Issue #199.
# --------------------------------------------------------------------------

@case("one code naming two different subjects", "title", 1)
def _():
    return tree({
        f"{U}/computer-science/2024/s03/01.md": doc("uchut346", "economics-for-engineers", "B."),
        f"{U}/chemical-engineering/2024/s03/01.md":
            doc("uchut346", "engineering-economics", "B.", branch="chemical-engineering"),
    })


@case("the same code with the same title is fine", "title", 0)
def _():
    return tree({
        f"{U}/computer-science/2024/s03/01.md": doc("uchut346", "economics-for-engineers", "B."),
        f"{U}/chemical-engineering/2024/s03/01.md":
            doc("uchut346", "economics-for-engineers", "B.", branch="chemical-engineering"),
    })


# --------------------------------------------------------------------------
# 3. Cross-branch drift. The uchut346 older-scheme body, PR #213.
# --------------------------------------------------------------------------

CURRENT = ("National income concepts GDP GNP NNP methods of estimation. "
           "Inflation causes effects measures monetary fiscal repo rate. "
           "Capital budgeting time value of money net present value payback.")
OLD_SCHEME = ("Monetary system money functions central banking deflation. "
              "Taxation direct indirect GST. Stock market SENSEX NIFTY demat "
              "trading accounts problems faced by Indian stock market.")


@case("same code and title, different scheme's syllabus", "drift", 1)
def _():
    return tree({
        f"{U}/computer-science/2024/s03/01.md": doc("uchut346", "economics-for-engineers", CURRENT),
        f"{U}/chemical-engineering/2024/s03/01.md":
            doc("uchut346", "economics-for-engineers", OLD_SCHEME, branch="chemical-engineering"),
    })


@case("reworded but equivalent bodies do not drift", "drift", 0)
def _():
    reordered = " ".join(reversed(CURRENT.split(". "))) + "."
    return tree({
        f"{U}/computer-science/2024/s03/01.md": doc("uchut346", "economics-for-engineers", CURRENT),
        f"{U}/chemical-engineering/2024/s03/01.md":
            doc("uchut346", "economics-for-engineers", reordered, branch="chemical-engineering"),
    })


@case("a code in one branch only cannot drift", "drift", 0)
def _():
    return tree({f"{U}/computer-science/2024/s03/01.md":
                 doc("pccst302", "theory-of-computation", CURRENT)})


# --------------------------------------------------------------------------
# 4. Truncation. The "cost-benefit analysis, capit" defect, PR #213.
# --------------------------------------------------------------------------

@case("the real defect: last line breaks the section's punctuation habit",
      "truncation", 1)
def _():
    body = ("## Module 4\n\n"
            "- Value analysis and value engineering, cost value, use value.\n"
            "- Aims, advantages, and application areas of value engineering.\n"
            "- Value engineering procedure.\n"
            "- Break-even analysis, cost-benefit analysis, capit\n")
    return tree({f"{U}/computer-science/2024/s03/01.md": doc("x101", "t", body)})


@case("a bullet list that never punctuates is not truncated", "truncation", 0)
def _():
    body = ("## Module 1\n\n"
            "- Logic gates, universal gates\n"
            "- Adders, subtractors, multiplexers\n"
            "- Flip-flops, counters, registers\n"
            "- Simple sequential circuits using HDL\n")
    return tree({f"{U}/computer-science/2024/s03/01.md": doc("x101", "t", body)})


@case("a reference list ending in a year is not truncated", "truncation", 0)
def _():
    body = ("## References\n\n"
            "- *Engineering Economy* - Leland Blank, McGraw Hill, 7/e\n"
            "- *Indian Financial System* - M.Y. Khan, Tata McGraw Hill, 2011\n"
            "- *Engineering Economics* - R. Paneerselvam, PHI, 2012\n")
    return tree({f"{U}/computer-science/2024/s03/01.md": doc("x101", "t", body)})


@case("a fully punctuated section is not truncated", "truncation", 0)
def _():
    body = ("## Module 2\n\n"
            "- Cost concepts, private cost and social cost.\n"
            "- Revenue concepts and types of firms.\n"
            "- Markets, perfect competition and monopoly.\n")
    return tree({f"{U}/computer-science/2024/s03/01.md": doc("x101", "t", body)})


@case("two lines are too few to establish a habit", "truncation", 0)
def _():
    # Long enough that the thin-module rule stays out of the way: this case
    # is about the truncation rule declining to guess from two lines.
    body = ("## Module 1\n\n"
            "Number systems, binary and hexadecimal, base conversion.\n"
            "Basic gates, inverter, AND gate, OR gate, NAND gate and XOR gate\n")
    return tree({f"{U}/computer-science/2024/s03/01.md": doc("x101", "t", body)})


@case("a thin module heading with no syllabus", "truncation", 1)
def _():
    body = "## Course Modules\n\n### Module 1\n\nTBD\n"
    return tree({f"{U}/computer-science/2024/s03/01.md": doc("x101", "t", body)})


# --------------------------------------------------------------------------
# 5. Unsafe bytes, and the missing-course signal (gaest305, PR #212).
# --------------------------------------------------------------------------

@case("non-ASCII text is read fine and never flagged", "unsafe", 0)
def _():
    body = "Credits 2 · Cost – revenue – break-even. Don’t cares."
    return tree({f"{U}/computer-science/2024/s03/01.md":
                 doc("x101", "t", body).encode("utf-8")})


@case("a NUL byte is an error", "unsafe", 1)
def _():
    return tree({f"{U}/computer-science/2024/s03/01.md":
                 doc("x101", "t", "Body.").encode("utf-8").replace(b"Body", b"Bo\x00dy")})


@case("a branch missing courses against its peers", "coverage", 1)
def _():
    files = {}
    for branch in ("computer-science", "chemical-engineering", "civil-engineering"):
        for n in range(1, 6):
            files[f"{U}/{branch}/2024/s03/0{n}.md"] = doc(
                f"{branch[:2]}30{n}", "t", "Body.", branch=branch)
    for n in (4, 5):                      # thin out one branch
        del files[f"{U}/civil-engineering/2024/s03/0{n}.md"]
    return tree(files)


@case("branches of naturally different size are not flagged", "coverage", 0)
def _():
    files = {}
    for branch in ("computer-science", "chemical-engineering", "civil-engineering"):
        for n in range(1, 6):
            files[f"{U}/{branch}/2024/s03/0{n}.md"] = doc(
                f"{branch[:2]}30{n}", "t", "Body.", branch=branch)
    del files[f"{U}/civil-engineering/2024/s03/05.md"]
    return tree(files)


RUNNERS = {
    "duplicate": lambda rs, fs: audit.check_duplicate_codes(rs),
    "title": lambda rs, fs: audit.check_title_conflicts(rs),
    "drift": lambda rs, fs: audit.check_body_drift(rs),
    "truncation": lambda rs, fs: audit.check_truncation_and_thinness(rs),
    "coverage": lambda rs, fs: audit.check_coverage_outliers(rs),
    "unsafe": lambda rs, fs: fs,
}


def main():
    failed = 0
    cwd = os.getcwd()
    for name, check, expected, build in CASES:
        root = build()
        try:
            os.chdir(root)
            records, findings = audit.collect("universities")
            got = len(RUNNERS[check](records, findings))
        finally:
            os.chdir(cwd)
            shutil.rmtree(root, ignore_errors=True)
        ok = got == expected
        failed += 0 if ok else 1
        print(f"  {'PASS' if ok else 'FAIL'}  {check:<11} "
              f"expected={expected} got={got}  {name}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
