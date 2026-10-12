import sys
import fitz

doc = fitz.open(sys.argv[1])
page = doc[0]
blocks = page.get_text("dict")["blocks"]
for b in blocks:
    if "lines" in b:
        for l in b["lines"]:
            for s in l["spans"]:
                print(f"[{s['size']:.1f}pt] {s['text']}")
