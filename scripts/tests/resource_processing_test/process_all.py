#!/usr/bin/env python3
"""
One-command resource processing pipeline.

Usage:
  python process_all.py                     # Auto-process all files in input/
  python process_all.py myfile.pptx         # Process a specific file
  python process_all.py input/pptx/lecture.pptx
  python process_all.py --correct           # Auto-process + open correction tool for low-scoring files
  python process_all.py --interactive       # Step through each file with correction prompt

What it does:
  1. Finds the input file(s)
  2. Runs UnifiedContentProcessor (text extraction + image extraction + OCR)
  3. Generates quality metrics
  4. Saves report to output/reports/
  5. Optionally opens correction tool for files with score < threshold
  6. Analyzes accumulated corrections for self-improvement suggestions
  7. Prints summary with quality scores
"""

import argparse
import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(dotenv_path=_PROJECT_ROOT / ".env")

SUPPORTED_EXTS = {".pdf", ".pptx", ".docx", ".txt", ".md", ".png", ".jpg", ".jpeg"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tiff"}


def find_files(target: str = "") -> list[Path]:
    base_dir = Path(__file__).parent
    input_dir = base_dir / "input"

    if target:
        candidate = Path(target)
        if not candidate.is_absolute():
            candidate = base_dir / candidate
        if not candidate.exists():
            print(f"File not found: {candidate}")
            sys.exit(1)
        return [candidate.resolve()]

    files = []
    for f in sorted(input_dir.rglob("*")):
        if (
            f.is_file()
            and not f.name.startswith(".")
            and not f.name.startswith("~$")
            and f.suffix.lower() in SUPPORTED_EXTS
        ):
            files.append(f)
    return files


def process_and_report(file_path: Path, polish: bool = False) -> dict:
    from app.processing.unified_processor import UnifiedContentProcessor

    fmt = file_path.suffix.lower()
    print(f"\n{'=' * 60}")
    print(f"  Processing: {file_path.name}")
    print(f"  Format: {fmt.upper()}")
    print(f"{'=' * 60}")

    processor = UnifiedContentProcessor(use_polish=polish)

    t0 = time.time()
    bundle = processor.extract(str(file_path), resource_id=file_path.stem)
    elapsed = time.time() - t0

    lines = bundle.markdown.split("\n")
    headings = [l for l in lines if l.startswith("#")]
    list_items = [l for l in lines if l.strip().startswith("- ") or l.strip().startswith("1. ")]
    images_count = len(bundle.images)

    print(f"\n  Results:")
    print(f"  {'Processing path:':<20} {bundle.processing_path}")
    print(f"  {'Time:':<20} {elapsed:.2f}s")
    print(f"  {'Lines:':<20} {len(lines)}")
    print(f"  {'Headings:':<20} {len(headings)}")
    print(f"  {'List items:':<20} {len(list_items)}")
    print(f"  {'Images extracted:':<20} {images_count}")

    diagram_images = [img for img in bundle.images if getattr(img, "is_diagram", True)]
    decorative_ignored = len(bundle.images) - len(diagram_images)
    if decorative_ignored > 0:
        print(f"  {'Decorative filtered:':<20} {decorative_ignored}")

    if bundle.warnings:
        for w in bundle.warnings:
            print(f"  ⚠  {w}")

    from scripts.resource_processing_test.test_harness.metrics import QualityMetrics
    metrics = QualityMetrics().compute(
        markdown=bundle.markdown,
        format_type=fmt,
    )
    metrics["processing_time_s"] = round(elapsed, 2)

    print(f"\n  {'Score':<20} {'Value':<10} {'Grade':<10}")
    print(f"  {'─' * 40}")
    score = metrics.get("overall_score", 1.0)
    grade = "A" if score >= 0.9 else ("B" if score >= 0.75 else ("C" if score >= 0.5 else "D"))
    print(f"  {'Overall':<20} {score:<10.4f} {grade:<10}")
    print(f"  {'Structural validity':<20} {metrics.get('structural_validity', 0):<10.2f}")
    print(f"  {'Consistency':<20} {metrics.get('consistency_score', 0):<10.2f}")

    output_dir = Path(__file__).parent / "output" / "reports"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_md = output_dir / f"OUTPUT_{file_path.stem}.md"
    output_md.write_text(bundle.markdown, encoding="utf-8")
    print(f"\n  Output: {output_md}")

    try:
        from app.processing.pipeline_knowledge import PipelineKnowledge
        PipelineKnowledge().record_performance(score, int(elapsed * 1000))
    except Exception:
        pass

    from scripts.resource_processing_test.test_harness.reporter import Reporter
    expected_dir = Path(__file__).parent / "expected"
    expected_file = expected_dir / f"{file_path.stem}.md"
    if expected_file.exists():
        from scripts.resource_processing_test.test_harness.diff_engine import DiffEngine
        expected = expected_file.read_text(encoding="utf-8")
        diff = DiffEngine().compare(bundle.markdown, expected)
        print(f"  Expected comparison: similarity {diff.similarity_ratio:.2%}")
        if diff.missing_images:
            print(f"  Missing images: {len(diff.missing_images)}")

    return {
        "file": str(file_path),
        "format": fmt,
        "score": score,
        "grade": grade,
        "metrics": metrics,
        "warnings": bundle.warnings,
        "images": images_count,
        "elapsed": elapsed,
        "markdown": bundle.markdown,
    }


def run_correction_tool(file_path: Path):
    output_dir = Path(__file__).parent / "output" / "reports"
    output_md = output_dir / f"OUTPUT_{file_path.stem}.md"
    expected_md = Path(__file__).parent / "expected" / f"{file_path.stem}.md"

    if not output_md.exists():
        print(f"  No output found for {file_path.name}. Process it first.")
        return

    expected_arg = f" --expected \"{expected_md}\"" if expected_md.exists() else ""
    print(f"\n  Opening correction tool for {file_path.name}...")
    os.system(f"python3 \"{Path(__file__).parent / 'correction_tool.py'}\" \"{output_md}\"{expected_arg}")


def print_final_summary(results: list[dict]):
    print(f"\n{'=' * 60}")
    print(f"  FINAL SUMMARY")
    print(f"{'=' * 60}")
    print(f"  {'File':<40} {'Score':<8} {'Grade':<6} {'Images':<8} {'Time':<8}")
    print(f"  {'─' * 70}")

    for r in results:
        fname = Path(r["file"]).name[:38]
        print(f"  {fname:<40} {r['score']:<8.4f} {r['grade']:<6} {r['images']:<8} {r['elapsed']:.2f}s")

    print(f"  {'─' * 70}")
    avg_score = sum(r["score"] for r in results) / max(len(results), 1)
    total_images = sum(r["images"] for r in results)
    total_time = sum(r["elapsed"] for r in results)
    total_warnings = sum(len(r["warnings"]) for r in results)
    overall_grade = "A" if avg_score >= 0.9 else ("B" if avg_score >= 0.75 else ("C" if avg_score >= 0.5 else "D"))
    print(f"  {'AVERAGE':<40} {avg_score:<8.4f} {overall_grade:<6} {total_images:<8} {total_time:.2f}s")
    print(f"  Files: {len(results)}, Warnings: {total_warnings}")
    print(f"{'=' * 60}")

    from scripts.resource_processing_test.test_harness.reporter import Reporter
    quality_dir = Path(__file__).parent / "quality_reports"
    historical = Reporter().load_historical_reports(str(quality_dir))
    if len(historical) >= 2:
        trend = Reporter().compute_trend(historical)
        print(f"  Historical trend: {trend.get('direction', 'stable')} "
              f"({trend.get('change', 0):+.4f} over {trend.get('runs', 0)} runs)")


def run_self_improvement():
    corrections_dir = Path(__file__).parent / "corrections"
    if corrections_dir.exists() and any(corrections_dir.iterdir()):
        print(f"\n{'=' * 60}")
        print(f"  SELF-IMPROVEMENT ANALYSIS")
        print(f"{'=' * 60}")
        from scripts.resource_processing_test.analyze_corrections import analyze, suggest_tweaks, persist_to_knowledge
        analysis = analyze(str(corrections_dir))
        if analysis:
            persist_to_knowledge(analysis, str(corrections_dir))
        suggestions = suggest_tweaks(str(corrections_dir))
        if suggestions:
            print(f"\n  Suggested tweaks:")
            for s in suggestions:
                print(f"    [{s['confidence']:.0%}] {s['suggestion']}")
                print(f"           Target: {s['target']}")
    else:
        print(f"\n  No corrections yet. Use --correct to review and save corrections.")

    try:
        from app.processing.pipeline_knowledge import PipelineKnowledge
        knowledge = PipelineKnowledge()
        print(f"\n{'=' * 60}")
        print(f"  PIPELINE KNOWLEDGE STATE")
        print(f"{'=' * 60}")
        print(knowledge.summary())
        knowledge.reload()
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(
        description="One-command resource processing pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python process_all.py                     # Process ALL files in input/
  python process_all.py lecture.pptx        # Process a specific file
  python process_all.py --correct           # Process + open correction tool for low scores
  python process_all.py --interactive       # Step through each file with prompts
  python process_all.py --polish            # Run with AI polish pass (requires Ollama/API key)
"""
    )
    parser.add_argument("input", nargs="?", help="File to process (omit to process all in input/)")
    parser.add_argument("--correct", "-c", action="store_true", help="Open correction tool for files scoring below 0.9")
    parser.add_argument("--interactive", "-i", action="store_true", help="Prompt before each file, offer correction")
    parser.add_argument("--polish", "-p", action="store_true", help="Enable AI polish pass")
    parser.add_argument("--skip-analysis", action="store_true", help="Skip self-improvement analysis")
    parser.add_argument("--workers", "-w", type=int, default=1, help="Number of parallel workers (default: 1)")
    args = parser.parse_args()

    files = find_files(args.input)

    if not files:
        print("No files found.")
        sys.exit(1)

    print(f"Found {len(files)} file(s) to process")
    if args.polish:
        print("AI polish: enabled")

    results = []

    if args.workers > 1 and not args.interactive and not args.correct:
        import concurrent.futures
        print(f"Running in parallel with {args.workers} workers... (Console output may be interleaved)")
        
        with concurrent.futures.ProcessPoolExecutor(max_workers=args.workers) as executor:
            future_to_file = {executor.submit(process_and_report, f, args.polish): f for f in files}
            for future in concurrent.futures.as_completed(future_to_file):
                file_path = future_to_file[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as exc:
                    print(f"File {file_path.name} generated an exception: {exc}")
    else:
        for file_path in files:
            if args.interactive:
                resp = input(f"\nProcess {file_path.name}? [Y/n/q]: ").strip().lower()
                if resp == "q":
                    break
                if resp == "n":
                    continue
    
            result = process_and_report(file_path, polish=args.polish)
            results.append(result)

        if args.correct and result["score"] < 0.9:
            resp = input(f"\n  Score {result['score']:.2f} is below threshold. Open correction tool? [Y/n]: ").strip().lower()
            if resp != "n":
                run_correction_tool(file_path)

        if args.interactive:
            input("  Press Enter to continue...")

    if results:
        print_final_summary(results)

    if not args.skip_analysis:
        run_self_improvement()

    print(f"\nDone. All output in: {Path(__file__).parent / 'output' / 'reports'}")


if __name__ == "__main__":
    main()
