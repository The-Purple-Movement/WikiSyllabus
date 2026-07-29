#!/usr/bin/env python3
"""Convert a KTU 2024 scheme course block into a WikiSyllabus markdown file.

Reads the pdftotext -layout dump of a branch syllabus PDF, isolates one
course by its code, and emits the repo's file format. Records the source
so provenance is never guessed at.

Usage:
    python3 convert_ktu.py <dump.txt> <COURSE_CODE> <semester> <branch-slug>
"""
import re
import sys


def slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[–—]", "-", text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return re.sub(r"-{2,}", "-", text).strip("-")


def course_block(text: str, code: str) -> str:
    """Text from this course's title down to the next course or semester."""
    anchor = text.find(f"Course Code")
    idx = None
    for m in re.finditer(r"Course Code\s+" + re.escape(code) + r"\b", text):
        idx = m.start()
        break
    if idx is None:
        raise SystemExit(f"course code {code} not found")

    start = max(0, idx - 900)
    head = text[start:idx]
    sem_marks = [m.end() for m in re.finditer(r"SEMESTER\s+S?\d\b", head)]
    if sem_marks:
        start = start + sem_marks[-1]

    rest = text[idx + 20:]
    nxt = re.search(r"Course Code\s+[A-Z]{2,6}[LT]?\d{3}", rest)
    end = idx + 20 + (nxt.start() if nxt else len(rest))
    return text[start:end]


def title_of(block: str) -> str:
    for line in block.split("\n"):
        s = line.strip()
        if len(s) < 6 or s.startswith(("(", "Course", "Teaching", "Credits", "Prereq")):
            continue
        if s.upper() == s and re.search(r"[A-Z]{3}", s):
            return re.sub(r"\s{2,}", " ", s)
    return ""


# KTU prints titles in all caps, so .title() would render DBMS as "Dbms".
ACRONYMS = {
    "ai", "ml", "dbms", "os", "hdl", "sql", "nosql", "iot", "it", "cs", "vlsi",
    "nlp", "api", "ui", "ux", "gpu", "cpu", "rf", "vr", "ar", "2d", "3d",
}


def pretty(title: str) -> str:
    return " ".join(
        w.upper() if w.lower().strip("()") in ACRONYMS else w.capitalize()
        for w in title.split()
    )


def section(block: str, start_pat: str, stop_pats) -> str:
    m = re.search(start_pat, block, re.I)
    if not m:
        return ""
    tail = block[m.end():]
    cut = len(tail)
    for p in stop_pats:
        s = re.search(p, tail, re.I)
        if s:
            cut = min(cut, s.start())
    return tail[:cut].strip()


NOISE = re.compile(
    r"^(Course Code|Teaching Hours|Credits|Prerequisites|CIE|ESE|Exam Hours|\(L:"
    r"|SEMESTER|Experiments?$|Expt\.?$|No\.?$|Module$|Contact$|Hours$"
    r"|Module\s+Contact$|No\.?\s+Hours$"
    r"|Syllabus Description$|Total$|Page \d+)",
    re.I,
)


def clean_lines(chunk: str):
    """Drop table furniture and join wrapped continuation lines."""
    out = []
    for raw in chunk.split("\n"):
        s = re.sub(r"\s{2,}", " ", raw).strip()
        if not s or NOISE.match(s):
            continue
        starts_item = bool(re.match(r"^([\d]+[.)]?\s|[●•\-*])", s))
        if out and not starts_item and s[:1].islower():
            out[-1] = out[-1].rstrip() + " " + s  # wrapped line
        else:
            out.append(re.sub(r"^([\d]+[.)]|[●•*])\s*", "", s))
    return [o for o in out if len(o) > 3]


ABBREV = re.compile(r"(?:\b(?:i\.e|e\.g|etc|vs|Dr|Mr|Ms|No|Fig|Eq)\.|\b[A-Za-z]\.)$", re.I)


def sentence_closed(text: str) -> bool:
    """True when text ends a sentence, ignoring abbreviations like 'i.e.'."""
    text = text.rstrip()
    if not text or text[-1] not in ".?!":
        return False
    return not ABBREV.search(text)


def numbered_rows(chunk: str):
    """Parse a KTU table whose row number may sit alone on its own line.

    A number alone on a line is vertically centred in its cell, so the text
    around it belongs to that row. A number followed by text starts its row
    on the same line.
    """
    rows, buf, cur = {}, [], None
    for raw in chunk.split("\n"):
        s = re.sub(r"\s{2,}", " ", raw).strip()
        if not s or NOISE.match(s):
            continue
        lone = re.match(r"^(\d{1,2})$", s)
        inline = re.match(r"^(\d{1,2})\s+(\S.*)$", s)
        if lone or inline:
            n = int((lone or inline).group(1))
            # Row numbers are centred in their cell, so buffered text can
            # belong to either side: keep feeding the previous row until its
            # sentence closes, then the rest is this row's text above its number.
            head = []
            if cur is not None:
                for line in buf:
                    prev = " ".join(rows[cur]).rstrip()
                    if head or sentence_closed(prev):
                        head.append(line)
                    else:
                        rows[cur].append(line)
            else:
                head = buf[:]
            buf = []
            cur = n
            rows[cur] = head + ([inline.group(2)] if inline else [])
        else:
            buf.append(s)
    if cur is not None:
        rows[cur].extend(buf)
    merged = []
    for n in sorted(rows):
        text = " ".join(rows[n]).strip()
        text = re.sub(r"\s{2,}", " ", text)
        if len(text) > 3:
            merged.append((n, text))
    return merged


# A module marker line: the row number, optionally the middle line of that
# row's text, then the contact-hours figure pushed to the far right column.
MODULE_MARK = re.compile(r"^\s{0,20}(\d)\s+(?:(\S.*?)\s{3,})?(\d{1,3})\s*$")


def module_rows(chunk: str):
    """Parse a KTU theory syllabus table.

    Each module is a table row, and pdftotext centres the row number and its
    contact-hours figure vertically inside the cell, so they land partway
    through the module's own text rather than at its start. Blank lines fall
    both inside and between cells, so they cannot mark the boundary alone.

    What holds: a blank-line paragraph never straddles two modules, and a
    centred marker is nearest to its own row. So each paragraph is assigned to
    the marker it contains, or failing that to the closest marker by line.
    """
    lines = chunk.replace("\f", "\n\n").split("\n")

    # Markers must run 1, 2, 3... which rejects stray numeric lines that
    # happen to start with a digit and end with one.
    marks, expect = {}, 1
    for i, raw in enumerate(lines):
        m = MODULE_MARK.match(raw)
        if m and int(m.group(1)) == expect:
            marks[i] = (expect, m.group(2) or "")
            expect += 1
    if not marks:
        return []

    paras, cur = [], None
    for i, raw in enumerate(lines):
        if i in marks:
            text = marks[i][1]
        else:
            text = re.sub(r"\s{2,}", " ", raw).strip()
            if text and NOISE.match(text):
                continue
        if not text:
            cur = None
            continue
        if cur is None:
            cur = {"at": [i], "lines": []}
            paras.append(cur)
        cur["at"].append(i)
        # A line wrapped mid-sentence rejoins the one above it.
        if cur["lines"] and text[:1].islower():
            cur["lines"][-1] = cur["lines"][-1].rstrip() + " " + text
        else:
            cur["lines"].append(text)

    rows = {}
    for p in paras:
        owned = [marks[i][0] for i in p["at"] if i in marks]
        if owned:
            n = owned[0]
        else:
            mid = (p["at"][0] + p["at"][-1]) / 2
            n = marks[min(marks, key=lambda i: abs(i - mid))][0]
        rows.setdefault(n, []).extend(p["lines"])

    merged = []
    for n in sorted(rows):
        text = re.sub(r"\s{2,}", " ", " ".join(rows[n])).strip()
        if len(text) > 3:
            merged.append((n, text))
    return merged


def main():
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(2)
    dump, code, sem, branch = sys.argv[1], sys.argv[2].upper(), sys.argv[3], sys.argv[4]
    text = open(dump, encoding="utf-8", errors="ignore").read()
    block = course_block(text, code)

    title = title_of(block)
    ctype = "Lab" if re.search(r"Course Type\s+Lab", block, re.I) else "Theory"
    credits = ""
    cm = re.search(r"Credits\s+(\d+)", block)
    if cm:
        credits = cm.group(1)

    objectives = clean_lines(section(
        block, r"Course Objectives\s*:?",
        [r"\bSYLLABUS\b", r"Expt\.", r"Course Outcomes", r"Module\s*\n"],
    ))
    stops = [
        r"Course Outcomes", r"Text\s*Book", r"Reference", r"CO-PO",
        r"Assessment Pattern", r"Evaluation Pattern", r"Continuous Internal",
        r"Course Assessment Method",
        r"Total\s+\d+", r"Books?\s*\n",
    ]
    if ctype == "Lab":
        body_src = section(block, r"Expt\.?\s*\n|Experiments\s*\n", stops)
        body = numbered_rows(body_src)
    else:
        body_src = section(block, r"\bSYLLABUS\b", stops)
        body = module_rows(body_src)

    # KTU's table layouts vary enough that extraction cannot be trusted
    # unattended. Refuse to emit a file that looks wrong so the caller has to
    # transcribe this course by hand instead of committing a silent gap.
    problems = []
    if not title:
        problems.append("no course title found")
    if not body:
        problems.append("no syllabus body found")
    if ctype == "Theory":
        if len(body) < 4:
            problems.append(f"only {len(body)} modules (KTU theory courses have 4+)")
        thin = [n for n, txt in body if len(txt) < 120]
        if thin:
            problems.append(f"modules {thin} have too little text")
    elif len(body) < 5:
        problems.append(f"only {len(body)} experiments")
    if problems:
        sys.stderr.write(f"[convert_ktu] {code} REJECTED: {'; '.join(problems)}\n")
        sys.exit(1)

    lines = [
        "---",
        'country: "india"',
        'university: "ktu"',
        f'branch: "{branch}"',
        'version: "2024"',
        f"semester: {int(sem)}",
        f'course_code: "{code.lower()}"',
        f'course_title: "{slug(title)}"',
        'language: "english"',
        'contributor: "@deepusnath"',
        'provenance: "extracted-from-official-pdf"',
        'source: "KTU B.Tech Full Time 2024 Scheme, official branch syllabus PDF"',
        "---",
        "",
        f"# {code}: {pretty(title)}",
        "",
        f"**Course type:** {ctype}" + (f" · **Credits:** {credits}" if credits else ""),
        "",
    ]
    if objectives:
        lines += ["## Course Objectives", ""]
        for o in objectives:
            o = re.sub(r"^[\d]+\.\s*", "", o)
            lines.append(f"- {o}")
        lines.append("")
    if body:
        if ctype == "Lab":
            lines += ["## Experiments", ""]
            for n, text in body:
                lines.append(f"{n}. {text}")
        else:
            lines += ["## Course Modules", ""]
            for n, text in body:
                lines += [f"### Module {n}", "", text, ""]
        lines.append("")

    sys.stdout.write("\n".join(lines).replace("\n\n\n", "\n\n"))


if __name__ == "__main__":
    main()
