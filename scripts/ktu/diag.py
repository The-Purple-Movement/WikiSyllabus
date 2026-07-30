"""Classify why theory-course extraction fails, across every cached branch dump."""
import glob, re, sys, collections
sys.path.insert(0, ".")
import convert_ktu as K

STOPS = [r"Course Outcomes", r"Text\s*Book", r"Reference", r"CO-PO", r"Assessment Pattern",
         r"Evaluation Pattern", r"Continuous Internal", r"Course Assessment Method",
         r"Total\s+\d+", r"Books?\s*\n"]


def load():
    """Yield (code, block) once per unique course code across all branches."""
    seen = set()
    for f in sorted(glob.glob("dumps/*.txt")):
        txt = open(f, encoding="utf-8", errors="ignore").read()
        for code in sorted(set(re.findall(r"Course Code\s+([A-Z]{2,6}[LT]?\d{3})", txt))):
            if code in seen:
                continue
            seen.add(code)
            try:
                yield code, f, K.course_block(txt, code)
            except SystemExit:
                pass


def classify(code, block):
    if re.search(r"Course Type\s+Lab", block, re.I):
        return "lab", None
    if not K.title_of(block):
        return "theory", "no-title"
    src = K.section(block, r"\bSYLLABUS\b", STOPS)
    if not src.strip():
        return "theory", "no-syllabus-section"
    rows = K.module_rows(src)
    if not rows:
        return "theory", "no-markers"
    if len(rows) < 4:
        return "theory", f"only-{len(rows)}-modules"
    thin = [n for n, t in rows if len(t) < 120]
    if thin:
        return "theory", "thin-module"
    return "theory", None


if __name__ == "__main__":
    kinds = collections.Counter()
    examples = collections.defaultdict(list)
    for code, f, block in load():
        kind, why = classify(code, block)
        kinds[(kind, why)] += 1
        if why:
            examples[why].append((code, f))
    total_t = sum(v for (k, w), v in kinds.items() if k == "theory")
    ok_t = kinds[("theory", None)]
    print(f"theory: {ok_t}/{total_t} pass ({ok_t/total_t*100:.0f}%)\n")
    for (k, w), v in sorted(kinds.items(), key=lambda x: -x[1]):
        if k == "theory" and w:
            print(f"  {v:5}  {w:22} e.g. {', '.join(c for c,_ in examples[w][:4])}")
