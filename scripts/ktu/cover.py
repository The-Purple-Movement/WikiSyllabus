"""Check that module text accounts for the source table, losing nothing."""
import re, sys, collections
sys.path.insert(0, ".")
import convert_ktu as K
import diag


def norm(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).split()


def check(block):
    src = K.section(block, r"\bSYLLABUS\b", diag.STOPS)
    rows = K.module_rows(src)
    if not rows:
        return None
    # Source words, minus table furniture, the right-aligned hours column, and
    # the module numbers themselves (consumed as markers, not content).
    lines = src.replace("\f", "\n\n").split("\n")
    marks = K.module_markers(lines)
    keep = []
    for i, raw in enumerate(lines):
        t = marks[i][1] if i in marks else re.sub(r"\s{2,}", " ", K.drop_hours(raw)).strip()
        if t and not K.NOISE.match(t):
            keep.append(t)
    want = collections.Counter(norm(" ".join(keep)))
    got = collections.Counter(norm(" ".join(t for _, t in rows)))
    missing = sum((want - got).values())
    extra = sum((got - want).values())
    return len(want.values()) and sum(want.values()), missing, extra


if __name__ == "__main__":
    worst, stats = [], collections.Counter()
    for code, f, block in diag.load():
        if re.search(r"Course Type\s+Lab", block, re.I):
            continue
        r = check(block)
        if r is None:
            continue
        total, missing, extra = r
        stats["courses"] += 1
        if missing == 0 and extra == 0:
            stats["exact"] += 1
        else:
            worst.append((missing + extra, code, f, total, missing, extra))
    print(f"theory courses with a parsed body: {stats['courses']}")
    print(f"  word-for-word identical to source: {stats['exact']} ({stats['exact']/stats['courses']*100:.0f}%)")
    worst.sort(reverse=True)
    print(f"  differing: {len(worst)}")
    for d, code, f, total, m, e in worst[:8]:
        print(f"    {code:10} {f:24} src={total:5} missing={m:4} extra={e:4}")
