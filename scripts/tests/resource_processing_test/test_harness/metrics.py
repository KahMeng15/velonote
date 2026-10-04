"""Quality metrics computation for resource processing output."""

import os
import re


class QualityMetrics:

    def compute(self, markdown: str, expected: str = "", images: list = None,
                expected_images: list = None, format_type: str = "") -> dict:
        lines = markdown.split("\n")
        non_empty = [l for l in lines if l.strip()]

        headings = [l for l in lines if l.startswith("#")]
        h1 = [l for l in headings if l.startswith("# ")]
        h2 = [l for l in headings if l.startswith("## ")]
        h3 = [l for l in headings if l.startswith("### ")]

        list_items = [l for l in lines if l.strip().startswith("- ")]
        ordered_items = [l for l in lines if re.match(r"^\d+[.)]\s", l.strip())]

        tables = [l for l in lines if l.strip().startswith("|")]
        code_blocks = self._count_code_blocks(markdown)

        images_found = []
        for m in re.finditer(r"!\[(.*?)\]\((.+?)\)", markdown):
            images_found.append({"alt": m.group(1), "src": m.group(2)})

        body = [l for l in non_empty if not l.startswith("#") and not l.strip().startswith("- ")
                and not re.match(r"^\d+[.)]\s", l.strip()) and not l.strip().startswith("|")
                and not l.strip().startswith("```")]

        metrics = {
            "basic": {
                "total_lines": len(lines),
                "non_empty_lines": len(non_empty),
                "headings": len(headings),
                "h1": len(h1),
                "h2": len(h2),
                "h3": len(h3),
                "list_items": len(list_items),
                "ordered_items": len(ordered_items),
                "body_lines": len(body),
                "table_rows": len(tables),
                "code_blocks": code_blocks,
                "images": len(images_found),
            }
        }

        if expected:
            expected_lines = expected.split("\n")
            expected_non_empty = [l for l in expected_lines if l.strip()]
            recall = len(non_empty) / max(len(expected_non_empty), 1)
            if recall > 1.0:
                recall = 1.0 / recall
            metrics["content_preservation"] = round(min(recall, 1.0), 4)

        metrics["images_extracted"] = len(images_found) if images_found else 0
        if expected_images:
            found_srcs = {img["src"] for img in images_found}
            expected_srcs = set(expected_images)
            metrics["image_recall"] = len(found_srcs & expected_srcs) / max(len(expected_srcs), 1)
            metrics["image_noise"] = len(found_srcs - expected_srcs) / max(len(found_srcs), 1)
        else:
            metrics["image_recall"] = 1.0 if not expected_images else 0.0
            metrics["image_noise"] = 0.0

        from .diff_engine import compute_structural_validity
        structural = compute_structural_validity(markdown)
        metrics["structural_validity"] = structural["score"]
        metrics["structural_issues"] = structural["issues"]

        consistency_score = 1.0
        if structural.get("list_consistency_issues"):
            consistency_score -= 0.1 * len(structural["list_consistency_issues"])
        metrics["consistency_score"] = max(0.0, consistency_score)

        metrics["overall_score"] = self._compute_overall(metrics)

        return metrics

    def _count_code_blocks(self, markdown: str) -> int:
        count = 0
        in_block = False
        for line in markdown.split("\n"):
            if line.strip().startswith("```"):
                in_block = not in_block
                count += 1
        return count // 2

    def _compute_overall(self, metrics: dict) -> float:
        weights = {
            "content_preservation": 0.25,
            "structural_validity": 0.25,
            "consistency_score": 0.15,
            "image_recall": 0.15,
            "image_noise": 0.10,
        }
        score = 0.0
        total_weight = 0.0
        for key, weight in weights.items():
            val = metrics.get(key, 1.0)
            if key == "image_noise":
                val = 1.0 - val
            score += val * weight
            total_weight += weight

        if total_weight == 0:
            return 1.0

        unweighted = (
            metrics.get("basic", {}).get("headings", 0) > 0
            and metrics.get("basic", {}).get("list_items", 0) >= 0
        )
        if not unweighted:
            score *= 0.8

        return round(min(score / total_weight, 1.0), 4)

    def compute_ocr_confidence(self, markdown: str) -> float:
        confs = []
        for line in markdown.split("\n"):
            m = re.search(r"<!-- ocr-conf:\s*([\d.]+)\s*-->", line)
            if m:
                confs.append(float(m.group(1)))
        if confs:
            return sum(confs) / len(confs)
        return 1.0
