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

## What it does not do

**It does not guess.** The converter refuses to emit a file whose extraction
looks wrong: no title, no syllabus body, a theory course with fewer than four
modules, a module with implausibly little text, or a lab with fewer than five
experiments. A rejected course must be transcribed by hand from the PDF. This
is deliberate. A silently truncated module is worse than a missing file,
because nobody goes looking for it.

Measured on the CSE 2024 branch PDF (96 courses): 58% pass the gate, 42% are
rejected and need hand transcription. Machine time is negligible (about 22 ms
per course); the real cost of this pipeline is human verification, and the
gate exists to tell you exactly which courses need it.

The rejection rate is a property of KTU's table layouts, which vary between
courses. Three distinct table shapes are handled so far:

- experiments tables with the row number alone on its own line
- theory tables with the module number, mid-cell text, and contact hours
  sharing one line
- (unhandled) lab tables that split into Part A / Part B / Part C with
  `A1.` / `B1.` style labels, e.g. PCCSL308

Improving coverage means adding parsers for more shapes, not loosening the
gate.

## Provenance

Every generated file records `provenance: "extracted-from-official-pdf"` and
the source scheme. Hand-transcribed files record
`provenance: "transcribed-from-official-pdf"`. Neither claim is made for
content that did not come from the official PDF.
