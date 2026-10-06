"""
Extracts raw markdown (no AI polish) from files dropped into the local workspace.
Use this instead of the database-driven script to manually process specific files.
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from app.processing.unified_processor import UnifiedContentProcessor

WORKSPACE_DIR = Path(__file__).parent.parent / "workspace"
INPUT_DIR = WORKSPACE_DIR / "input"
RAW_DIR = WORKSPACE_DIR / "raw"

RAW_DIR.mkdir(parents=True, exist_ok=True)

def process_file(file_path: Path):
    resource_id = file_path.stem.replace(" ", "_")
    
    # Mirror the folder structure
    rel_dir = file_path.parent.relative_to(INPUT_DIR)
    target_dir = RAW_DIR / rel_dir
    target_dir.mkdir(parents=True, exist_ok=True)
    
    out_path = target_dir / f"{resource_id}_raw.md"
    
    if out_path.exists():
        print(f"Skipping {file_path.name} — raw file already exists.")
        return

    print(f"Processing {file_path.name}...")
    try:
        processor = UnifiedContentProcessor(use_polish=False)
        bundle = processor.extract(str(file_path), resource_id)
        
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(bundle.markdown)
        print(f"✅ Saved to {out_path}")
    except Exception as e:
        print(f"❌ Failed to process {file_path.name}: {e}")

def main():
    files = [f for f in INPUT_DIR.rglob("*") if f.is_file() and not f.name.startswith(".")]
    
    if not files:
        print(f"No files found in {INPUT_DIR}.")
        print("Drop PDFs, PPTXs, or images there and run again.")
        return

    for file_path in files:
        process_file(file_path)
        
    print("\nNext step: Copy files from workspace/raw/ to workspace/polished/ and fix them manually.")

if __name__ == "__main__":
    main()
