"""Report generation for test harness runs."""

import json
import os
from datetime import datetime
from typing import Optional


class Reporter:

    def __init__(self, output_dir: str = "output/reports"):
        self.output_dir = output_dir

    def generate_report(self, results: list[dict], run_config: Optional[dict] = None) -> dict:
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H%M%S")
        report = {
            "timestamp": timestamp,
            "config": run_config or {},
            "files": results,
            "summary": self._compute_summary(results),
        }

        os.makedirs(self.output_dir, exist_ok=True)
        report_path = os.path.join(self.output_dir, f"report_{timestamp}.json")
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)

        return report

    def _compute_summary(self, results: list[dict]) -> dict:
        if not results:
            return {"files_processed": 0}

        scores = [r.get("metrics", {}).get("overall_score", 0) for r in results if r.get("metrics")]
        valid_scores = [s for s in scores if s is not None]

        total_images = sum(r.get("metrics", {}).get("basic", {}).get("images", 0) for r in results)
        total_warnings = sum(len(r.get("warnings", [])) for r in results)
        total_errors = sum(1 for r in results if r.get("error"))

        return {
            "files_processed": len(results),
            "files_with_errors": total_errors,
            "average_score": round(sum(valid_scores) / max(len(valid_scores), 1), 4) if valid_scores else 0,
            "max_score": round(max(valid_scores), 4) if valid_scores else 0,
            "min_score": round(min(valid_scores), 4) if valid_scores else 0,
            "total_images_extracted": total_images,
            "total_warnings": total_warnings,
        }

    def load_historical_reports(self, reports_dir: str = "quality_reports") -> list[dict]:
        reports = []
        if not os.path.exists(reports_dir):
            return reports

        for f in sorted(os.listdir(reports_dir)):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(reports_dir, f)) as fh:
                        reports.append(json.load(fh))
                except Exception:
                    continue
        return reports

    def compute_trend(self, reports: list[dict]) -> dict:
        if len(reports) < 2:
            return {"trend": "insufficient_data", "direction": "stable", "runs": len(reports)}

        scores = []
        for r in reports:
            s = r.get("summary", {}).get("average_score", 0)
            scores.append(s)

        recent = scores[-3:] if len(scores) >= 3 else scores
        older = scores[:-3] if len(scores) >= 3 else scores[:-1]

        avg_recent = sum(recent) / max(len(recent), 1)
        avg_older = sum(older) / max(len(older), 1)

        diff = avg_recent - avg_older
        direction = "up" if diff > 0.01 else ("down" if diff < -0.01 else "stable")

        return {
            "trend": direction,
            "direction": direction,
            "change": round(diff, 4),
            "recent_avg": round(avg_recent, 4),
            "older_avg": round(avg_older, 4),
            "runs": len(scores),
            "all_scores": [round(s, 4) for s in scores],
        }

    def print_summary_table(self, results: list[dict], trend: Optional[dict] = None):
        print()
        print("=" * 80)
        print(f"  Resource Processing Test — {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
        print("=" * 80)
        print(f"  {'File':<45} {'Format':<8} {'Score':<8} {'Images':<8} {'Warnings':<8}")
        print("  " + "-" * 77)

        for r in results:
            fname = os.path.basename(r.get("file", "unknown"))[:44]
            fmt = r.get("format", "?")
            metrics = r.get("metrics", {})
            score = f"{metrics.get('overall_score', 0):.2f}" if metrics.get('overall_score') is not None else "N/A"
            imgs = metrics.get('basic', {}).get('images', 0) if metrics.get('basic') else 0
            warns = len(r.get("warnings", []))
            err = " ERROR" if r.get("error") else ""
            print(f"  {fname:<45} {fmt:<8} {score:<8} {imgs:<8} {warns:<8}{err}")

        summary = self._compute_summary(results)
        print("  " + "-" * 77)
        print(f"  {'OVERALL':<45} {'':<8} {summary.get('average_score', 0):.2f}    "
              f"{summary.get('total_images_extracted', 0):<8} {summary.get('total_warnings', 0)}")
        print(f"  Files: {summary.get('files_processed', 0)}, Errors: {summary.get('files_with_errors', 0)}")

        if trend:
            print(f"  Trend: {trend.get('direction', 'stable')} "
                  f"({trend.get('change', 0):+.4f} over {trend.get('runs', 0)} runs)")
        print("=" * 80)
        print()

    def print_individual_report(self, result: dict):
        print(f"\n── {os.path.basename(result.get('file', 'unknown'))} ──")
        if result.get("error"):
            print(f"  ERROR: {result['error']}")
            return

        metrics = result.get("metrics", {})
        basic = metrics.get("basic", {})
        print(f"  Format: {result.get('format', '?')}")
        print(f"  Lines: {basic.get('total_lines', 0)} | "
              f"Headings: {basic.get('headings', 0)} | "
              f"Lists: {basic.get('list_items', 0)} | "
              f"Images: {basic.get('images', 0)}")
        print(f"  Score: {metrics.get('overall_score', 0):.4f} | "
              f"Structural: {metrics.get('structural_validity', 0):.2f} | "
              f"Consistency: {metrics.get('consistency_score', 0):.2f}")

        if result.get("warnings"):
            for w in result["warnings"]:
                print(f"  ⚠ {w}")

        structural_issues = metrics.get("structural_issues", [])
        if structural_issues:
            for issue in structural_issues[:5]:
                print(f"  ⚠ Structural: {issue}")

        if result.get("diff"):
            diff = result["diff"]
            if diff.get("missing_images"):
                for img in diff["missing_images"]:
                    print(f"  ⚠ Missing image: {img.get('src', '?')}")
            if diff.get("heading_diffs"):
                for hd in diff["heading_diffs"][:3]:
                    print(f"  ⚠ Heading: {hd.get('type', '?')}: '{hd.get('text', '')[:40]}'")
