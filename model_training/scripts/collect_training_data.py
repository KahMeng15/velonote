"""
Extracts raw markdown (no AI polish) from existing processed resources.
Run this to generate the "input" side of training pairs.
Then manually edit each output file to create the ideal "target" markdown.
"""

import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.processing.unified_processor import UnifiedContentProcessor
from app.utils.db import SessionLocal
from app.models.db import Resource

RAW_DIR = Path("data/training/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

def extract_raw(file_path: str, resource_id: str) -> str:
    """Extract markdown with AI polish disabled."""
    processor = UnifiedContentProcessor(use_polish=False)
    bundle = processor.extract(file_path, resource_id)
    return bundle.markdown

def main():
    """Dump raw markdown for all processed resources."""
    with SessionLocal() as db:
        resources = db.query(Resource).limit(200).all()

        for r in resources:
            out_path = RAW_DIR / f"{r.id}_raw.md"
            if out_path.exists():
                continue  # Skip already extracted

            file_path = r.file_path  # adjust to your actual field name
            if not Path(file_path).exists():
                continue

            print(f"Extracting {r.id}...")
            raw_md = extract_raw(file_path, r.id)

            with open(out_path, "w") as f:
                f.write(raw_md)

    print(f"Done. Files in {RAW_DIR}/")
    print("Now manually polish each *_raw.md file → save as data/training/polished/*_polished.md")

if __name__ == "__main__":
    main()
