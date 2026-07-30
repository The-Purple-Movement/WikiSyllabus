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


# A line carrying a module number in the left column: the digit, then either
# nothing or a wide gap and that row's text. The contact-hours figure is a
# separate column and does not reliably share the number's line, so it is
# stripped before matching rather than matched alongside.
NUM_LINE = re.compile(r"^(\s{0,24})([1-9])(?:\s{2,}(\S.*?))?\s*$")
HOURS = re.compile(r"\s{3,}(\d{1,3})\s*$")
# Left edge of the contact-hours column. Nothing this far right is prose.
HOURS_COL = 55


def drop_hours(raw: str) -> str:
    """Remove the right-aligned contact-hours figure from a table line.

    Tested on where the digits sit, not where the gap before them starts: on
    a line holding nothing but the hours figure the gap begins at column zero.
    """
    m = HOURS.search(raw)
    return raw[: m.start()] if m and m.start(1) >= HOURS_COL else raw


def module_markers(lines):
    """Locate the line holding each module's number.

    Numbers are not the only digits in the left column, so candidates are
    resolved as a whole: build the run 1, 2, 3... that stays in one column,
    and prefer the longest such run. A stray digit inside prose rarely has
    four consecutively-numbered siblings sitting at the same indent.
    """
    cands = []
    for i, raw in enumerate(lines):
        m = NUM_LINE.match(drop_hours(raw))
        if m:
            cands.append((i, int(m.group(2)), len(m.group(1)), m.group(3) or ""))

    best, best_score = [], None
    for start in [c for c in cands if c[1] == 1]:
        seq = [start]
        for n in range(2, 9):
            opts = [c for c in cands if c[1] == n and c[0] > seq[-1][0]]
            if not opts:
                break
            # Same left column as the run so far beats merely being next.
            opts.sort(key=lambda c: (abs(c[2] - start[2]) > 3, c[0]))
            seq.append(opts[0])
        spread = max(abs(c[2] - start[2]) for c in seq)
        score = (len(seq), -spread)
        if best_score is None or score > best_score:
            best, best_score = seq, score
    return {i: (n, text) for i, n, _, text in best}


# How hard the centred-marker geometry pushes back against the prose signals.
# Tuned against hand-verified boundaries in truth.py; see scripts/ktu/README.
W_ASYM = 0.45

# How close a rival layout may score before the split is called unreliable.
AMBIGUITY_MARGIN = 0.5

# Weight of the topic-heading signal. KTU modules usually open by naming their
# subject and following it with a colon ("Turbo codes: Turbo decoding, ...").
W_TOPIC = 4.0
TOPIC = re.compile(r"^[A-Z][^.]{0,45}?\s*:")


def module_rows(chunk: str, with_confidence=False):
    """Parse a KTU theory syllabus table.

    Each module is a table row, and pdftotext centres the row number and its
    contact-hours figure vertically inside the cell, so they land partway
    through the module's own text rather than at its start. Blank lines fall
    both inside and between cells, so they cannot mark the boundary alone.

    What holds: the marker sits near the middle of its own row, so the split
    between two consecutive modules lies somewhere between their markers.
    Which line exactly is decided by prose, not by arithmetic: a real cell
    boundary has a finished sentence above it and a fresh one below. Blank
    lines and the midpoint only break ties, because pdftotext emits blanks
    inside cells as readily as between them.
    """
    lines = chunk.replace("\f", "\n\n").split("\n")
    marks = module_markers(lines)
    if not marks:
        return ([], True) if with_confidence else []

    def shown(i):
        if i in marks:
            return marks[i][1]
        t = re.sub(r"\s{2,}", " ", drop_hours(lines[i])).strip()
        return "" if NOISE.match(t) else t

    # Right-hand edge of the text column. A line ending well short of it is
    # the last line of a wrapped block, which is where a cell tends to end.
    edges = [len(drop_hours(l).rstrip()) for l in lines if l.strip()]
    width = max(edges) if edges else 0

    # Running count of lines that carry text, so cell sizes can be compared
    # without blank padding (which varies per cell) distorting them.
    filled = [0]
    for i in range(len(lines)):
        filled.append(filled[-1] + bool(shown(i)))

    def prose(j, a, b):
        """How much line j looks like the seam between two cells, judged only
        on the text either side of it."""
        k_above = next((k for k in range(j - 1, a, -1) if shown(k)), None)
        above = shown(k_above) if k_above is not None else ""
        below = next((shown(k) for k in range(j, b + 1) if shown(k)), "")
        score = 0.0
        if above and sentence_closed(above):
            score += 3
        if below[:1].isupper():
            score += 2
        if not lines[j].strip():
            score += 1
        if k_above is not None and len(drop_hours(lines[k_above]).rstrip()) < 0.6 * width:
            score += 2
        # A bracketed reference such as "[Text 1: sections 3.1-3.4]" is a
        # footnote to the module above it, so it must not open the next.
        if below.startswith("["):
            score -= 4
        if TOPIC.match(below):
            score += W_TOPIC
        return score

    def lopsided(lo, a, hi):
        """How far marker a sits from the middle of the cell [lo, hi).

        Counted in lines carrying text: blank padding differs from cell to
        cell and would otherwise swamp the comparison.
        """
        return abs((filled[a] - filled[lo]) - (filled[hi] - filled[a + 1]))

    # Every boundary is chosen at once rather than one at a time. Taken
    # greedily, a locally tempting split leaves the *next* cell badly
    # off-centre, and by then the choice is already locked in.
    at = sorted(marks)
    start = next((i for i in range(len(lines)) if shown(i)), 0)
    end = len(lines)
    gaps = list(zip(at, at[1:]))

    def solve(banned=None):
        """Highest-scoring set of boundaries, optionally with one gap's
        neighbourhood ruled out so a rival layout can be costed."""
        layers, prev = [], {start: (0.0, None)}
        for g, (a, b) in enumerate(gaps):
            layer = {}
            for j in range(a + 1, b + 1):
                if banned and banned[0] == g and abs(j - banned[1]) <= 2:
                    continue
                gain = prose(j, a, b)
                best = max(
                    ((sc + gain - W_ASYM * lopsided(p, a, j), p)
                     for p, (sc, _) in prev.items() if p <= a),
                    default=None,
                )
                if best:
                    layer[j] = best
            if not layer:
                return None, []
            layers.append(layer)
            prev = layer
        score, cur = max(
            (sc - W_ASYM * lopsided(j, at[-1], end), j) for j, (sc, _) in prev.items()
        )
        chosen = []
        for layer in reversed(layers):
            chosen.append(cur)
            cur = layer[cur][1]
        return score, list(reversed(chosen))

    score, chosen = solve()
    if score is None:
        return ([], True) if with_confidence else []
    # If a materially different layout scores about as well, the table does
    # not say where the cells divide and no amount of tuning will reveal it.
    # Say so, rather than picking one and sounding certain.
    ambiguous = any(
        (rival := solve((g, j))[0]) is not None and rival >= score - AMBIGUITY_MARGIN
        for g, j in enumerate(chosen)
    )
    edges = [0] + chosen + [end]

    rows = {}
    for (n, _), lo, hi in zip((marks[i] for i in at), edges, edges[1:]):
        out = []
        for i in range(lo, hi):
            text = shown(i)
            if not text:
                continue
            # A line wrapped mid-sentence rejoins the one above it.
            if out and text[:1].islower():
                out[-1] = out[-1].rstrip() + " " + text
            else:
                out.append(text)
        rows[n] = out

    merged = []
    for n in sorted(rows):
        text = re.sub(r"\s{2,}", " ", " ".join(rows[n])).strip()
        if len(text) > 3:
            merged.append((n, text))
    return (merged, ambiguous) if with_confidence else merged


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
        body, unsure = module_rows(body_src, with_confidence=True)

    # KTU's table layouts vary enough that extraction cannot be trusted
    # unattended. Refuse to emit a file that looks wrong so the caller has to
    # transcribe this course by hand instead of committing a silent gap.
    problems = []
    if not title:
        problems.append("no course title found")
    if not body:
        problems.append("no syllabus body found")
    if ctype == "Theory":
        if unsure:
            problems.append("module boundaries are ambiguous; a rival split scores as well")
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
