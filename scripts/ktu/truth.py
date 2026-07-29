"""Hand-verified module boundaries, read off the source PDFs by eye.

Aggregate metrics are gameable: a heuristic can improve "modules starting
mid-sentence" while quietly splitting other courses in the wrong place. These
cases were checked against the printed table and pin the boundaries down.

Each entry is a course code mapped to the opening and closing words of every
module. Snippets, not line numbers, so they survive changes to how the
section is sliced out of the block.
"""
import re
import sys

sys.path.insert(0, ".")
import convert_ktu as K
import diag

TRUTH = {
    # Blank lines fall before markers 3 and 4, and module 2 ends on a short
    # line ("Cyclic Codes") that is easy to mistake for a continuation.
    "PECST414": [
        ("Binary block codes, Minimum distance", "Reed Muller codes"),
        ("Cyclic Codes : Generator and Parity-Check", "Shortened Cyclic Codes"),
        ("Convolutional codes: Encoding, state diagram", "bounds for convolutional codes"),
        ("Turbo codes: Turbo decoding", "Applications of linear codes"),
    ],
    # No blank lines at all between modules 1, 2 and 3.
    "PCAGT302": [
        ("Simple stresses and strains", "its simple applications"),
        ("Composite stresses and strains", "Point of contraflexure"),
        ("Bending stresses in beams", "open coiled springs derivation"),
        ("Deflections of beams relation between", "moment distribution method"),
    ],
    # Every module ends with a bracketed [Text N: ...] reference that belongs
    # to the module above it, not the one below.
    "GAMAT301": [
        ("Random variables, Discrete random variables", "3.1 to 3.4, 3.6, 5.1, 5.2"),
        ("Continuous random variables and their", "4.1, 4.2, 4.3, 4.4, 5.1, 5.2"),
        ("Limit theorems", "sections 2.7, 2.9, 5.3"),
        ("Markov Chains, Random Walk Model", "sections 4.1, 4.2, 4.3, 4.4"),
    ],
    # Bracketed references again, but with two blank lines mid-table and a
    # marker whose own line carries the middle of the sentence.
    "GBMAT401": [
        ("Random variables, Discrete random variables", "3.1 to 3.4, 3.6, 5.1, 5.2"),
        ("Continuous random variables and their", "4.1, 4.2, 4.3, 4.4, 5.1, 5.2"),
        ("Confidence Intervals, Confidence Level", "7.1, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4"),
        ("Random process concept", "Chapter 6"),
    ],
    # Markers start at column zero here, and cell heights differ a lot
    # (11, 8 and 14 contact hours), so the midpoint is a poor guide.
    "GAEST305": [
        ("Introduction to digital Systems", "the module, Verilog operators"),
        ("Combinational Logic Design", "Continuous assignment with delay"),
        ("MSI Logic and Digital Building Blocks", "adding delay to primitives"),
        ("Sequential Logic Design", "Modeling an FSM in Verilog"),
    ],
    # Blank lines both inside and between every cell.
    "OECMT615": [
        ("Introduction to Artificial Intelligence", "8-puzzle, 8-queens"),
        ("Searching", "Alpha beta pruning"),
        ("Knowledge-Based Agents", "Backward chaining"),
        ("Reinforcement Learning", "Applications of Reinforcement Learning"),
    ],
    # Contact-hours figures sit on their own lines, away from the numbers.
    "OEAGT611": [
        ("Types and quality of plastics", "nursery bags, trays etc"),
        ("Plastics as cladding material", "food grains in open"),
        ("Use of plastics as alternate material", "in plasticutlure applications"),
        ("Water management", "canal, pond and reservoir"),
    ],
}


# The same branch is published as more than one PDF, and the renderings
# differ. This one is the source the shipped CSE files were built from, so it
# has to be pinned separately from the dumps/ corpus.
EXTRA = {
    "PECST414": ("cse.txt", [
        ("Binary block codes, Minimum distance", "Reed Muller codes"),
        ("Cyclic Codes : Generator and Parity-Check", "Shortened Cyclic Codes"),
        ("Convolutional codes: Encoding, state diagram", "bounds for convolutional codes"),
        ("Turbo codes: Turbo decoding", "Applications of linear codes"),
    ]),
}


def words(s):
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def run(verbose=False):
    blocks = {c: b for c, _, b in diag.load() if c in TRUTH}
    cases = dict(TRUTH)
    for code, (src, expected) in EXTRA.items():
        text = open(src, encoding="utf-8", errors="ignore").read()
        blocks[code + "@" + src] = K.course_block(text, code)
        cases[code + "@" + src] = expected

    total = hits = 0
    for code, expected in cases.items():
        rows = K.module_rows(K.section(blocks[code], r"\bSYLLABUS\b", diag.STOPS))
        got = [t for _, t in rows]
        for i, (head, tail) in enumerate(expected):
            total += 2
            actual = got[i] if i < len(got) else ""
            ok_h = words(actual).startswith(words(head))
            ok_t = words(actual).endswith(words(tail))
            hits += ok_h + ok_t
            if verbose and not (ok_h and ok_t):
                print(f"  {code} M{i+1}: {'' if ok_h else 'HEAD '}{'' if ok_t else 'TAIL '}mismatch")
                print(f"     want {head!r} ... {tail!r}")
                print(f"     got  {actual[:60]!r} ... {actual[-40:]!r}")
    print(f"ground truth: {hits}/{total} boundaries correct ({hits/total*100:.0f}%)")
    return hits, total


if __name__ == "__main__":
    run(verbose=True)
