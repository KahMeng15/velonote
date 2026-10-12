#!/usr/bin/env python3
"""
Smart Pipeline Test Script

Tests the multi-method extraction pipeline on a file inside the `input` directory
and saves the result and detailed debug logs to the `output` directory.
"""

import sys
import os
import logging
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

# Load .env from the project root so GEMINI_API_KEY is picked up
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")

def configure_logging(log_file: Path):
    """Set up logging to go to both console and a debug log file."""
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)

    # Clear existing handlers
    logger.handlers.clear()

    # File handler (detailed debug)
    fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(fh)

    # Console handler (clean info)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)

def main():
    """Run the smart pipeline on the input file."""
    # Ensure directories exist
    base_dir = Path(__file__).parent
    input_dir = base_dir / "input"
    output_dir = base_dir / "output"
    input_dir.mkdir(exist_ok=True)
    output_dir.mkdir(exist_ok=True)

    log_file = output_dir / "debug_log.txt"
    configure_logging(log_file)

    # .env already loaded at module level; no need to call load_dotenv() again

    # Parse optional CLI file selection.
    target_input = None
    for idx, arg in enumerate(sys.argv):
        if arg == "--input" and idx + 1 < len(sys.argv):
            target_input = Path(sys.argv[idx + 1])
            break
        if arg.startswith("--input="):
            target_input = Path(arg.split("=", 1)[1])
            break

    # Find input files
    supported = [".pdf", ".pptx"]
    input_files = []

    if target_input:
        candidate = target_input
        if not candidate.is_absolute():
            candidate = (base_dir / candidate).resolve()
        if not candidate.exists():
            logging.error(f"❌ Input file not found: {candidate}")
            sys.exit(1)
        if candidate.suffix.lower() not in supported:
            logging.error(f"❌ Unsupported input file type: {candidate.suffix}. Supported: {', '.join(supported)}")
            sys.exit(1)
        input_files = [candidate]
    else:
        # Search recursively for supported files
        for f in input_dir.rglob("*"):
            if f.is_file() and f.suffix.lower() in supported and not f.name.startswith("~"):
                input_files.append(f)

    if not input_files:
        logging.error(f"❌ No supported files (PDF or PPTX) found in {input_dir}")
        sys.exit(1)

    logging.info(f"📄 Found {len(input_files)} files to process in {input_dir}")
    logging.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

    # Check for flags.
    use_polish = "--polish" in sys.argv

    # Parse --api-key=VALUE from argv
    cli_key = None
    for arg in sys.argv:
        if arg.startswith("--api-key="):
            cli_key = arg.split("=", 1)[1].strip()
            break

    gemini_key = cli_key or os.getenv("GEMINI_API_KEY") or os.getenv("GLOBAL_GEMINI_API_KEY") or os.getenv("GLOBAL_AI_TIER1_API_KEY")
    
    if use_polish and not gemini_key:
        logging.warning("⚠️  --polish requested but no GEMINI_API_KEY found. Skipping AI refinement.")

    # Initialize pipeline
    from app.processing.smart_pipeline import SmartPipeline
    
    gemini_model = os.getenv("GLOBAL_AI_TIER1_MODEL")

    pipeline = SmartPipeline(
        use_polish=use_polish and bool(gemini_key),
        gemini_api_key=gemini_key,
        gemini_model=gemini_model,
    )

    for i, input_file in enumerate(input_files, 1):
        try:
            logging.info(f"\n🚀 [{i}/{len(input_files)}] Running Smart Pipeline on: {input_file.name}")
            markdown = pipeline.process(str(input_file))

            # Save Markdown
            md_file = output_dir / f"OUTPUT_{input_file.stem}_smart.md"
            with open(md_file, "w", encoding="utf-8") as f:
                f.write(markdown)

            logging.info(f"\n✅ Done with {input_file.name}!")
            logging.info(f"   Markdown Output: {md_file}")

            # Print quality summary
            lines = markdown.split("\n")
            headings = [l for l in lines if l.startswith("#")]
            lists = [l for l in lines if l.strip().startswith("- ") or l.strip().startswith("1. ")]
            tables = [l for l in lines if l.strip().startswith("|")]
            body = [l for l in lines if l.strip() and not l.startswith("#") and not l.strip().startswith("-") and not l.strip().startswith("1.") and not l.strip().startswith("|")]

            logging.info(f"📊 Quality Metrics:")
            logging.info(f"   Headings:   {len(headings)}")
            logging.info(f"   List items: {len(lists)}")
            logging.info(f"   Table rows: {len(tables)}")
            logging.info(f"   Body text:  {len(body)}")
            logging.info(f"   Total lines: {len(lines)}")
            logging.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        except Exception as e:
            logging.error(f"\n❌ Error processing {input_file.name}: {e}", exc_info=True)
            logging.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
            continue

if __name__ == "__main__":
    main()
