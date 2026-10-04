"""
Combines raw + polished markdown pairs into train.jsonl / val.jsonl.
Run after manually curating polished versions.
"""

import json
import random
from pathlib import Path

RAW_DIR = Path("model_training/workspace/raw")
POLISHED_DIR = Path("model_training/workspace/polished")
OUTPUT_DIR = Path("model_training/workspace")

SYSTEM_PROMPT = """You are a markdown formatter for university lecture notes.
Given raw extracted markdown, output clean, consistently-styled markdown:
- Single # H1 for the document title (first line only)
- ## H2 for major topic sections
- ### H3 for subsections
- - bullet lists for enumerations (not pseudo-headings)
- Code blocks (```language) ONLY for actual code
- Preserve ALL content and exact words — no summarising
Output ONLY the markdown. No preamble. No explanation."""

def build():
    examples = []

    for raw_file in sorted(RAW_DIR.glob("*_raw.md")):
        resource_id = raw_file.stem.replace("_raw", "")
        polished_file = POLISHED_DIR / f"{resource_id}_polished.md"

        if not polished_file.exists():
            print(f"  SKIP {resource_id} — no polished version yet")
            continue

        raw = raw_file.read_text(encoding="utf-8").strip()
        polished = polished_file.read_text(encoding="utf-8").strip()

        if not raw or not polished:
            continue

        examples.append({
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": raw},
                {"role": "assistant", "content": polished},
            ]
        })

    random.shuffle(examples)
    split = int(len(examples) * 0.9)
    train, val = examples[:split], examples[split:]

    if not train:
        print("No pairs found. Make sure to create data/training/polished/*_polished.md files.")
        return

    (OUTPUT_DIR / "train.jsonl").write_text(
        "\n".join(json.dumps(e) for e in train)
    )
    (OUTPUT_DIR / "val.jsonl").write_text(
        "\n".join(json.dumps(e) for e in val)
    )

    print(f"✅ Built {len(train)} train + {len(val)} val examples")

if __name__ == "__main__":
    build()
