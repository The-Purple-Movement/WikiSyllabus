#!/usr/bin/env python3
"""Extract text from KTU 2024 scheme syllabus PDFs.

KTU's PDFs embed subset fonts whose character codes are the real ASCII
value minus 29, so a naive text dump reads as gibberish. This decodes
that, and falls back to pdftotext when it is installed.

Usage:
    python3 extract_ktu.py <file.pdf> [--raw]
"""
import re
import subprocess
import sys
import zlib

OFFSET = 29


def via_pdftotext(path):
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", path, "-"],
            capture_output=True, text=True, timeout=120,
        )
        if out.returncode == 0 and len(out.stdout.strip()) > 200:
            return out.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def unescape(raw: bytes) -> bytes:
    """Resolve PDF string escapes: \\n, \\(, \\) and octal \\ddd."""
    out = bytearray()
    i = 0
    while i < len(raw):
        c = raw[i]
        if c == 0x5C and i + 1 < len(raw):  # backslash
            nxt = raw[i + 1]
            if 0x30 <= nxt <= 0x37:  # octal, up to 3 digits
                digits = ""
                j = i + 1
                while j < len(raw) and len(digits) < 3 and 0x30 <= raw[j] <= 0x37:
                    digits += chr(raw[j])
                    j += 1
                out.append(int(digits, 8) & 0xFF)
                i = j
                continue
            simple = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12}
            out.append(simple.get(nxt, nxt))
            i += 2
            continue
        out.append(c)
        i += 1
    return bytes(out)


def decode_subset(text: bytes) -> str:
    """Shift character codes back into readable ASCII."""
    chars = []
    for b in text:
        shifted = b + OFFSET
        if 32 <= shifted <= 126:
            chars.append(chr(shifted))
        elif b in (10, 13, 32, 9):
            chars.append(" ")
    return "".join(chars)


def via_decode(path):
    data = open(path, "rb").read()
    pages = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", data, re.S):
        try:
            content = zlib.decompress(m.group(1))
        except zlib.error:
            continue
        parts = []
        for s in re.findall(rb"\((?:[^()\\]|\\.)*\)", content, re.S):
            parts.append(decode_subset(unescape(s[1:-1])))
        if parts:
            pages.append(" ".join(parts))
    return "\n\n=== PAGE BREAK ===\n\n".join(pages)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(2)
    path = sys.argv[1]
    raw = "--raw" in sys.argv

    text = None if raw else via_pdftotext(path)
    source = "pdftotext"
    if text is None:
        text = via_decode(path)
        source = "subset-decoder"

    sys.stderr.write(f"[extract_ktu] {path} via {source}, {len(text)} chars\n")
    print(text)


if __name__ == "__main__":
    main()
