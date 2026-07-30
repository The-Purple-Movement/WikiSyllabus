#!/usr/bin/env python3
"""Regression tests for the shadowed-frontmatter rule.

Scope is deliberately narrow: this covers the one rule added alongside the
KTU CSD 2024 repair. It is not a general test suite for the validator.

The rule exists because a repair once prepended a generated frontmatter block
onto files whose own block was merely missing its opening delimiter. The
danger in detecting that is `---`, which is also a Markdown horizontal rule
and appears in the body of more than a thousand files in this repository. Most
cases below are there to prove the rule does not fire on those.

Run:  python3 scripts/tests/test_shadowed_frontmatter.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from validate import shadowed_frontmatter  # noqa: E402

GOOD_BLOCK = """country: "india"
university: "ktu"
branch: "computer-science-and-design"
version: "2024"
semester: 3
course_code: "gamat301"
course_title: "mathematics-for-computer-and-information-science-3"
language: "english"
contributor: "@sandra07alex\""""

CASES = []


def case(name, expected):
    def wrap(fn):
        CASES.append((name, expected, fn()))
        return fn
    return wrap


@case("the real defect: a generated block shadowing the original", True)
def _():
    synthetic = GOOD_BLOCK.replace('"gamat301"', '"unknown"').replace(
        "@sandra07alex", "@backfill-needed")
    return f"---\n{synthetic}\n---\n\n{GOOD_BLOCK}\n---\n\n# GAMAT301: Maths\n\nBody.\n"


@case("a legitimate file with one frontmatter block", False)
def _():
    return f"---\n{GOOD_BLOCK}\n---\n\n# GAMAT301: Maths\n\nBody text here.\n"


@case("a horizontal rule in the body", False)
def _():
    return (f"---\n{GOOD_BLOCK}\n---\n\n# Course\n\n## Objectives\n\n"
            "Learn things.\n\n---\n\n## Modules\n\nModule 1.\n")


@case("a fenced example containing ---", False)
def _():
    return (f"---\n{GOOD_BLOCK}\n---\n\n# Course\n\nFrontmatter looks like this:\n\n"
            f"```yaml\n---\n{GOOD_BLOCK}\n---\n```\n\nEnd.\n")


@case("body prose starting with 'country:' then a later horizontal rule", False)
def _():
    return (f"---\n{GOOD_BLOCK}\n---\n\ncountry: this module covers country-level "
            "data modelling\n\nand more prose\n\n---\n\n## Next\n")


@case("an incomplete YAML-like block (missing required fields)", False)
def _():
    return (f"---\n{GOOD_BLOCK}\n---\n\ncountry: \"india\"\nuniversity: \"ktu\"\n"
            "---\n\n# Course\n")


@case("a second block with a duplicated field", False)
def _():
    dup = GOOD_BLOCK + '\nlanguage: "english"'
    return f"---\n{GOOD_BLOCK}\n---\n\n{dup}\n---\n\n# Course\n"


@case("a second block containing a blank line", False)
def _():
    holed = GOOD_BLOCK.replace('semester: 3', 'semester: 3\n')
    return f"---\n{GOOD_BLOCK}\n---\n\n{holed}\n---\n\n# Course\n"


@case("a file with no frontmatter at all", False)
def _():
    return "# Just a heading\n\nSome prose.\n\n---\n\nMore prose.\n"


@case("blank lines between the two blocks are still the defect", True)
def _():
    return f"---\n{GOOD_BLOCK}\n---\n\n\n\n{GOOD_BLOCK}\n---\n\n# Course\n"


@case("a metadata-shaped body closed by ---- is not a delimiter", False)
def _():
    return f"---\n{GOOD_BLOCK}\n---\n\n{GOOD_BLOCK}\n----\n\n# Course\n"


@case("a metadata-shaped body closed by ---text is not a delimiter", False)
def _():
    return f"---\n{GOOD_BLOCK}\n---\n\n{GOOD_BLOCK}\n---text\n\n# Course\n"


@case("a metadata-shaped body closed by '--- # comment' is not a delimiter", False)
def _():
    return f"---\n{GOOD_BLOCK}\n---\n\n{GOOD_BLOCK}\n--- # closing\n\n# Course\n"


@case("whitespace-only lines between the blocks are still blank", True)
def _():
    return f"---\n{GOOD_BLOCK}\n---\n   \n\t\n  \t  \n{GOOD_BLOCK}\n---\n\n# Course\n"


@case("a fenced yaml example immediately after the frontmatter", False)
def _():
    return (f"---\n{GOOD_BLOCK}\n---\n\n```yaml\n{GOOD_BLOCK}\n---\n```\n\n"
            "# Course\n\nBody.\n")


def main():
    failed = 0
    for name, expected, text in CASES:
        got = shadowed_frontmatter(text)
        ok = got == expected
        if not ok:
            failed += 1
        print(f"  {'PASS' if ok else 'FAIL'}  expected={expected!s:5} got={got!s:5}  {name}")
    print(f"\n{len(CASES) - failed}/{len(CASES)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
