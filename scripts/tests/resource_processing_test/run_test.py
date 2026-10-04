#!/usr/bin/env python3
"""
Resource Processing Test Suite.

Comprehensive test harness for the UnifiedContentProcessor pipeline.
Supports all formats: PDF, PPTX, DOCX, TXT, images.
Validates output against expected markdown, computes quality metrics,
and generates detailed reports.
"""

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")

from scripts.resource_processing_test.test_harness.diff_engine import DiffEngine
from scripts.resource_processing_test.test_harness.metrics import QualityMetrics
from scripts.resource_processing_test.test_harness.reporter import Reporter

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = {".pdf", ".pptx", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg"}


def configure_logging(log_file: Path, verbose: bool = False):
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.handlers.clear()
    fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
    logger.addHandler(fh)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(ch)


def get_files(input_dir: Path, target: str = "", format_filter: str = "") -> list[Path]:
    if target:
        candidate = Path(target)
        if not candidate.is_absolute():
            candidate = (input_dir.parent / candidate).resolve()
        if not candidate.exists():
            print(f"File not found: {candidate}")
            sys.exit(1)
        return [candidate]

    files = []
    for f in sorted(input_dir.rglob("*")):
        if not f.is_file() or f.name.startswith(".") or f.name.startswith("~$"):
            continue
        if f.suffix.lower() in SUPPORTED_EXTS:
            if format_filter:
                ext_map = {
                    "pdf": ".pdf", "pptx": ".pptx", "docx": ".docx",
                    "txt": ".txt", "image": tuple(IMAGE_EXTS),
                }
                expected = ext_map.get(format_filter.lower())
                if expected:
                    if isinstance(expected, tuple):
                        if f.suffix.lower() not in expected:
                            continue
                    elif f.suffix.lower() != expected:
                        continue
            files.append(f)
    return files


def detect_format(file_path: Path) -> str:
    ext = file_path.suffix.lower()
    if ext == ".pdf":
        return "PDF"
    elif ext == ".pptx":
        return "PPTX"
    elif ext == ".docx":
        return "DOCX"
    elif ext in (".txt", ".md"):
        return "TXT"
    elif ext in IMAGE_EXTS:
        return "Image"
    return "Unknown"


def load_expected(expected_dir: Path, file_path: Path) -> str:
    expected_file = expected_dir / f"{file_path.stem}.md"
    if expected_file.exists():
        return expected_file.read_text(encoding="utf-8")
    alt = expected_dir / file_path.with_suffix(".md").name
    if alt.exists():
        return alt.read_text(encoding="utf-8")
    return ""


def process_file(file_path: Path, use_polish: bool, expected_dir: Path,
                 output_dir: Path, resource_id: str = "") -> dict:
    fmt = detect_format(file_path)
    result = {"file": str(file_path), "format": fmt, "warnings": [], "metrics": {}}

    expected = load_expected(expected_dir, file_path)
    output_md = output_dir / f"OUTPUT_{file_path.stem}.md"

    try:
        from app.processing.unified_processor import UnifiedContentProcessor
        processor = UnifiedContentProcessor(use_polish=use_polish)

        t0 = time.time()
        bundle = processor.extract(str(file_path), resource_id=resource_id)
        elapsed = time.time() - t0

        output_md.parent.mkdir(parents=True, exist_ok=True)
        output_md.write_text(bundle.markdown, encoding="utf-8")

        metrics_calc = QualityMetrics()
        metrics = metrics_calc.compute(
            markdown=bundle.markdown,
            expected=expected,
            format_type=fmt,
        )
        metrics["processing_time_s"] = round(elapsed, 2)

        if bundle.processing_path == "scanned_ocr":
            ocr_conf = metrics_calc.compute_ocr_confidence(bundle.markdown)
            metrics["ocr_confidence"] = ocr_conf

        result["metrics"] = metrics
        result["processing_path"] = bundle.processing_path
        result["warnings"] = bundle.warnings

        if expected:
            diff_engine = DiffEngine()
            diff = diff_engine.compare(bundle.markdown, expected)
            result["diff"] = {
                "similarity_ratio": diff.similarity_ratio,
                "total_diff_lines": diff.total_diff_lines,
                "heading_diffs": diff.heading_diffs[:10],
                "missing_images": diff.missing_images,
                "extra_images": diff.extra_images,
                "list_boundary_diffs": diff.list_boundary_diffs[:5],
            }

        if bundle.images:
            result["images"] = [
                {"id": getattr(img, "id", ""), "path": getattr(img, "file_path", ""),
                 "type": getattr(img, "source_shape_type", "unknown"),
                 "diagram": getattr(img, "is_diagram", False)}
                for img in bundle.images
            ]

    except Exception as e:
        logger.error(f"Error processing {file_path.name}: {e}", exc_info=True)
        result["error"] = str(e)

    return result


def save_quality_report(report: dict, quality_dir: Path):
    quality_dir.mkdir(parents=True, exist_ok=True)
    timestamp = report.get("timestamp", "unknown")
    path = quality_dir / f"report_{timestamp}.json"
    with open(path, "w") as f:
        json.dump(report, f, indent=2, default=str)


def main():
    parser = argparse.ArgumentParser(description="Resource Processing Test Suite")
    parser.add_argument("--input", "-i", type=str, help="Specific file to process")
    parser.add_argument("--format", "-f", type=str, choices=["pdf", "pptx", "docx", "txt", "image"],
                        help="Filter by format")
    parser.add_argument("--polish", action="store_true", help="Enable AI polish pass")
    parser.add_argument("--expected-dir", type=str, default="expected",
                        help="Directory containing expected .md outputs")
    parser.add_argument("--output-dir", type=str, default="output",
                        help="Directory for generated outputs")
    parser.add_argument("--quality-dir", type=str, default="quality_reports",
                        help="Directory for historical quality reports")
    parser.add_argument("--verbose", "-v", action="store_true", help="Detailed logging")
    parser.add_argument("--historical", action="store_true",
                        help="Compare against previous quality reports")
    parser.add_argument("--analyze-corrections", action="store_true",
                        help="Analyze accumulated corrections after run")
    parser.add_argument("--resource-id", type=str, default="",
                        help="Resource ID for image storage (optional)")
    args = parser.parse_args()

    base_dir = Path(__file__).parent
    input_dir = base_dir / "input"
    expected_dir = base_dir / (args.expected_dir if Path(args.expected_dir).is_absolute()
                               else args.expected_dir)
    output_dir = base_dir / (args.output_dir if Path(args.output_dir).is_absolute()
                             else args.output_dir) / "reports"
    debug_dir = base_dir / (args.output_dir if Path(args.output_dir).is_absolute()
                            else args.output_dir) / "debug"
    quality_dir = base_dir / (args.quality_dir if Path(args.quality_dir).is_absolute()
                              else args.quality_dir)

    debug_dir.mkdir(parents=True, exist_ok=True)
    log_file = debug_dir / "debug_log.txt"
    configure_logging(log_file, args.verbose)

    files = get_files(input_dir, args.input, args.format or "")
    if not files:
        print(f"No supported files found in {input_dir}")
        sys.exit(1)

    print(f"Found {len(files)} file(s) to process")
    if args.polish:
        print("AI polish: enabled")

    reporter = Reporter(output_dir=str(output_dir))
    results = []

    for i, file_path in enumerate(files, 1):
        print(f"\n[{i}/{len(files)}] Processing: {file_path.name}")
        result = process_file(
            file_path, args.polish, expected_dir, output_dir,
            resource_id=args.resource_id or file_path.stem
        )

        results.append(result)
        reporter.print_individual_report(result)

        if result.get("error"):
            logger.error(f"Failed: {result['error']}")

    trend = None
    if args.historical:
        historical = reporter.load_historical_reports(str(quality_dir))
        trend = reporter.compute_trend(historical)
        reporter.print_summary_table(results, trend)
    else:
        reporter.print_summary_table(results)

    report = reporter.generate_report(results, run_config=vars(args))
    save_quality_report(report, quality_dir)

    print(f"\nReport saved: {reporter.output_dir}")

    if args.analyze_corrections:
        corrections_dir = base_dir / "corrections"
        if corrections_dir.exists():
            try:
                from scripts.resource_processing_test.analyze_corrections import analyze
                analyze(str(corrections_dir))
            except ImportError:
                print("Correction analyzer not available. Run correction_tool.py first to create corrections.")

    errors = [r for r in results if r.get("error")]
    if errors:
        print(f"\n{len(errors)} file(s) had errors. Check debug log for details.")
        sys.exit(1)


if __name__ == "__main__":
    main()
