#!/usr/bin/env python3
"""
Self-Improvement Engine — Analyzes accumulated corrections, identifies patterns,
and suggests pipeline parameter adjustments.

Usage:
  python analyze_corrections.py                          # Analyze all corrections
  python analyze_corrections.py --suggest-tweaks         # Output suggested parameter changes
  python analyze_corrections.py --apply-safe             # Auto-apply safe parameter tweaks
  python analyze_corrections.py --corrections-dir <path> # Custom corrections directory
"""

import argparse
import hashlib
import json
import logging
import os
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def load_corrections(corrections_dir: str) -> list[dict]:
    corrections = []
    if not os.path.exists(corrections_dir):
        print(f"Corrections directory not found: {corrections_dir}")
        return corrections

    for f in sorted(Path(corrections_dir).glob("*.json")):
        try:
            with open(f) as fh:
                data = json.load(fh)
                corrections.append(data)
        except Exception as e:
            print(f"  Warning: Could not read {f}: {e}")
    return corrections


def analyze(corrections_dir: str) -> dict:
    corrections = load_corrections(corrections_dir)
    if not corrections:
        print("No correction files found.")
        return {}

    total_files = len(corrections)
    all_corrections = []
    for c in corrections:
        all_corrections.extend(c.get("corrections", []))

    total_individual = len(all_corrections)
    type_counts = Counter(c.get("type", "unknown") for c in all_corrections)
    source_types = _infer_source_types(all_corrections)

    print()
    print("=" * 60)
    print("  Correction Analysis Report")
    print("=" * 60)
    print(f"  Total correction files:  {total_files}")
    print(f"  Total corrections:       {total_individual}")
    print()

    print(f"  {'Type':<25} {'Count':<8} {'%':<8}")
    print(f"  {'─' * 41}")
    for t, count in type_counts.most_common():
        pct = (count / total_individual) * 100
        bars = "█" * int(pct / 5)
        print(f"  {t:<25} {count:<8} {pct:.1f}% {bars}")
    print()

    if source_types:
        print(f"  {'Source Type':<25} {'Count':<8}")
        print(f"  {'─' * 33}")
        for st, count in source_types.most_common():
            print(f"  {st:<25} {count:<8}")

    return {
        "total_files": total_files,
        "total_corrections": total_individual,
        "type_counts": dict(type_counts),
        "source_types": dict(source_types),
    }


def _infer_source_types(corrections: list[dict]) -> Counter:
    ext_counts = Counter()
    for c in corrections:
        text = c.get("text", "") or c.get("from", "")
        if any(kw in text.lower() for kw in ["slide", "slide number"]):
            ext_counts["PPTX"] += 1
        elif any(kw in text.lower() for kw in ["page", "figure", "chapter"]):
            ext_counts["PDF"] += 1
        elif any(kw in text.lower() for kw in ["ocr", "conf"]):
            ext_counts["Scanned"] += 1
        else:
            ext_counts["Unknown"] += 1
    return ext_counts


def persist_to_knowledge(analysis: dict, corrections_dir: str):
    """Write analysis results into pipeline_knowledge.json so the pipeline reads them."""
    knowledge_path = Path(__file__).parent / "pipeline_knowledge.json"
    try:
        if knowledge_path.exists():
            with open(knowledge_path) as f:
                knowledge = json.load(f)
        else:
            knowledge = {}

        knowledge["version"] = knowledge.get("version", 1) + 1
        knowledge["last_updated"] = datetime.utcnow().isoformat()
        knowledge["total_correction_files"] = analysis.get("total_files", 0)
        knowledge["total_corrections_processed"] = analysis.get("total_corrections", 0)

        corrections = load_corrections(corrections_dir)
        all_corrections = [c for corr in corrections for c in corr.get("corrections", [])]

        type_counts = analysis.get("type_counts", {})
        cp = knowledge.setdefault("correction_patterns", {})
        for t, count in type_counts.items():
            pattern = cp.setdefault(t, {"count": 0, "by_format": {}})
            pattern["count"] = count

        # Extract heading adjustments to tune thresholds
        heading_corrections = [c for c in all_corrections
                               if c.get("type") in ("heading_level", "mark_heading")]
        if len(heading_corrections) >= 3:
            h1_count = sum(1 for c in heading_corrections if c.get("from") == "h2" and c.get("to") == "h1")
            h2_count = sum(1 for c in heading_corrections if c.get("from") == "h3" and c.get("to") == "h2")
            if h1_count > len(heading_corrections) * 0.3:
                current = knowledge.setdefault("heading_thresholds", {}).get("pptx_h1_multiplier", 1.6)
                knowledge["heading_thresholds"]["pptx_h1_multiplier"] = round(current + 0.05, 2)
                logger.info(f"Tuning: raised PPTX H1 threshold to {knowledge['heading_thresholds']['pptx_h1_multiplier']}")
            if h2_count > len(heading_corrections) * 0.3:
                current = knowledge.setdefault("heading_thresholds", {}).get("pptx_h2_multiplier", 1.3)
                knowledge["heading_thresholds"]["pptx_h2_multiplier"] = round(current + 0.05, 2)
                logger.info(f"Tuning: raised PPTX H2 threshold to {knowledge['heading_thresholds']['pptx_h2_multiplier']}")

        # Extract image skips — compute MD5 from file path so should_skip_image(md5_hash) works
        ignore_images = [c for c in all_corrections if c.get("type") == "ignore_image"]
        if len(ignore_images) >= 2:
            skip_list = knowledge.setdefault("skip_images_md5", [])
            for c in ignore_images:
                img_path = c.get("image_path", "")
                if not img_path:
                    continue
                try:
                    with open(img_path, "rb") as f:
                        md5_hash = hashlib.md5(f.read()).hexdigest()
                except (FileNotFoundError, IOError):
                    logger.warning(f"Cannot compute MD5 for '{img_path}' — file not found")
                    continue
                if md5_hash not in skip_list:
                    skip_list.append(md5_hash)
                    logger.info(f"Tuning: added MD5 {md5_hash[:12]}... to image skip list (from '{img_path}')")

        with open(knowledge_path, "w") as f:
            json.dump(knowledge, f, indent=2)

        print(f"\n  Knowledge file updated: {knowledge_path.name}")
        print(f"  Version {knowledge['version']} — {knowledge['total_corrections_processed']} total corrections")

    except Exception as e:
        print(f"  Warning: Could not update knowledge file: {e}")


def suggest_tweaks(corrections_dir: str) -> list[dict]:
    corrections = load_corrections(corrections_dir)
    if not corrections:
        return []

    all_corrections = [c for corr in corrections for c in corr.get("corrections", [])]
    suggestions = []

    heading_corrections = [c for c in all_corrections
                           if c.get("type") in ("heading_level", "mark_heading")]
    if len(heading_corrections) >= 3:
        suggestions.append({
            "target": "SmartPipeline.pptx_heading_thresholds",
            "suggestion": "Review PPTX heading thresholds — multiple heading level corrections suggest thresholds are too aggressive",
            "confidence": min(len(heading_corrections) / 20, 0.95),
            "correction_count": len(heading_corrections),
        })

    ignore_image_corrections = [c for c in all_corrections if c.get("type") == "ignore_image"]
    if len(ignore_image_corrections) >= 2:
        repeated_paths = Counter(c.get("image_path", "") for c in ignore_image_corrections)
        for path, count in repeated_paths.most_common(3):
            if count >= 2:
                suggestions.append({
                    "target": f"ImageClassifier.skip_images",
                    "suggestion": f"Add '{path}' to permanent skip list (ignored {count} times)",
                    "confidence": min(count / 5, 0.95),
                    "correction_count": count,
                })

    ocd_corrections = [c for c in all_corrections if c.get("type") == "ocr_correction"]
    if len(ocd_corrections) >= 3:
        suggestions.append({
            "target": "ImagePreprocessor.clahe_clip_limit",
            "suggestion": "OCR corrections suggest preprocessing needs tuning — increase CLAHE clip limit for better handwriting recognition",
            "confidence": min(len(ocd_corrections) / 15, 0.85),
            "correction_count": len(ocd_corrections),
        })

    list_corrections = [c for c in all_corrections
                        if c.get("type") in ("mark_list", "mark_olist", "mark_body")]
    if len(list_corrections) >= 3:
        suggestions.append({
            "target": "SignalMerger.list_detection",
            "suggestion": "List boundary corrections suggest list detection heuristics need adjustment",
            "confidence": min(len(list_corrections) / 15, 0.85),
            "correction_count": len(list_corrections),
        })

    return suggestions


def apply_safe_tweaks(corrections_dir: str, dry_run: bool = True):
    suggestions = suggest_tweaks(corrections_dir)
    if not suggestions:
        print("No tweaks to apply.")
        return

    print()
    print("=" * 60)
    print("  Suggested Pipeline Tweaks")
    print("=" * 60)

    for s in suggestions:
        bar = "█" * int(s["confidence"] * 20)
        print(f"\n  [{bar:<20}] {s['confidence']:.0%} confidence")
        print(f"  Target: {s['target']}")
        print(f"  Suggestion: {s['suggestion']}")
        print(f"  Based on {s['correction_count']} corrections")

    if dry_run:
        print(f"\n  {'─' * 50}")
        print("  DRY RUN — No changes applied. Use --apply to apply safe tweaks.")
    else:
        print(f"\n  {'─' * 50}")
        print("  APPLY mode — Changes would be applied (not yet implemented).")

    print()


def main():
    parser = argparse.ArgumentParser(description="Self-Improvement Engine")
    parser.add_argument("--corrections-dir", "-d", type=str, default="",
                        help="Directory with correction files")
    parser.add_argument("--suggest-tweaks", "-s", action="store_true",
                        help="Show suggested pipeline parameter changes")
    parser.add_argument("--apply-safe", action="store_true",
                        help="Auto-apply safe parameter tweaks")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Show what would be changed without applying (default: True)")
    parser.add_argument("--persist", "-p", action="store_true", default=True,
                        help="Write results to pipeline_knowledge.json (default: True)")
    args = parser.parse_args()

    base_dir = Path(__file__).parent
    corrections_dir = args.corrections_dir or str(base_dir / "corrections")

    analysis = analyze(corrections_dir)

    if analysis and args.persist:
        persist_to_knowledge(analysis, corrections_dir)

    if args.suggest_tweaks or args.apply_safe:
        apply_safe_tweaks(corrections_dir, dry_run=not args.apply_safe)


if __name__ == "__main__":
    main()
