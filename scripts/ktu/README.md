# KTU syllabus extraction

Tooling that turns an official KTU branch syllabus PDF into WikiSyllabus
course files. Written for the B.Tech Full Time 2024 Scheme, but the shape
of the problem is common to any university that publishes syllabi as
layout-formatted PDFs.

## Usage

```bash
pdftotext -layout Cse.pdf cse.txt
python3 scripts/ktu/convert_ktu.py cse.txt PCCSL307 3 computer-science \
  > universities/a-p-j-abdul-kalam-technological-university/computer-science/2024/s03/08.md
python3 scripts/validate.py <the file you just wrote>
```

`extract_ktu.py` is a fallback for PDFs where `pdftotext` is unavailable or
returns gibberish. Some KTU PDFs embed subset fonts whose character codes are
the real ASCII value minus 29; that script decodes them.

## The hard part: where does a module end?

Each module is a row in a table, and `pdftotext -layout` gives no row borders.
Worse, it centres the row number and the contact-hours figure vertically
inside the cell, so they land partway through the module's own text rather
than at its start, and they do not reliably share a line with each other.

Three signals decide the split, and none is sufficient alone:

1. **Prose.** A real cell boundary has a finished sentence above it and a
   fresh one below, and KTU modules usually open by naming their subject
   followed by a colon ("Turbo codes: Turbo decoding, ...").
2. **Geometry.** The number is centred, so a split leaving it lopsided in its
   cell is probably wrong. Measured in lines that carry text, because blank
   padding differs from cell to cell.
3. **Joint choice.** Boundaries are picked all at once, not left to right. A
   locally tempting split leaves the *next* cell badly off-centre, and taken
   greedily that decision is already locked in by the time it shows.

Blank lines are deliberately *not* treated as boundaries. `pdftotext` emits
them inside cells as readily as between them, and relying on them was the
single biggest source of wrong splits.

## What it does not do

**It does not guess.** The converter refuses to emit a file when extraction
looks wrong: no title, no syllabus body, a theory course with fewer than four
modules, a module with implausibly little text, or a lab with fewer than five
experiments.

It also refuses when the answer is **ambiguous**: if a materially different
set of boundaries scores about as well as the chosen one, the table does not
say where the cells divide, and no amount of tuning will reveal it. Those
courses are reported rather than quietly split one way and presented with
confidence.

A rejected course must be transcribed by hand.

## Measured, over all 40 branch PDFs of the 2024 scheme

3,003 course entries across branches deduplicate to 1,845 unique course codes.

| | Accepted | Rejected for hand work |
|---|---|---|
| Labs | 167 / 187 (89%) | 20 |
| Theory | 1,338 / 1,658 (81%) | 320, of which 182 are ambiguous rather than malformed |
| **Total** | **1,505 / 1,845 (82%)** | **340** |

Running the gate over the entire scheme takes about 4 seconds. Machine time
is not the constraint; human verification is, and the gate exists to name
exactly which courses need it.

## Checking the output

Three harnesses, in increasing order of what they can prove. They read PDF
text dumps, so put the branch PDFs and their `pdftotext -layout` output
alongside the scripts first.

```bash
python3 diag.py     # why extraction fails, grouped by cause
python3 cover.py    # is any source text lost or invented?
python3 truth.py    # do the splits land where a human puts them?
```

`cover.py` checks that the module text is word-for-word the source table with
nothing dropped and nothing added. It currently reports 1,627 / 1,627 exact.
That is a real guarantee, but a narrow one: text can be conserved perfectly
and still be filed under the wrong module.

`truth.py` is the one that matters. It holds module boundaries read off the
printed tables by eye, for eight courses chosen to span the different table
shapes. Aggregate metrics are gameable, and were gamed during development: an
early heuristic cut "modules starting mid-sentence" from 19% to 0.03% while
silently breaking courses that had parsed correctly before. Without
hand-verified cases that regression was invisible.

The remaining `truth.py` failure is PCAGT302, where two different splits score
identically on every signal available in the text dump; telling them apart
needs subject knowledge the parser does not have. The gate flags that course
as ambiguous, so it is rejected rather than shipped wrong. That is the
intended behaviour, not a known bug.

## Provenance

Every generated file records `provenance: "extracted-from-official-pdf"` and
the source scheme. Hand-transcribed files record
`provenance: "transcribed-from-official-pdf"`. Neither claim is made for
content that did not come from the official PDF.
