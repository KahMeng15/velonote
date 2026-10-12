"""Structural and content diff engine for comparing extracted vs expected markdown."""

import difflib
import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class StructuralDiff:
    heading_diffs: list = field(default_factory=list)
    list_boundary_diffs: list = field(default_factory=list)
    image_position_diffs: list = field(default_factory=list)
    content_diffs: list = field(default_factory=list)
    missing_images: list = field(default_factory=list)
    extra_images: list = field(default_factory=list)
    total_diff_lines: int = 0
    unified_diff: str = ""
    similarity_ratio: float = 0.0


@dataclass
class HeadingNode:
    level: int
    text: str
    line: int
    children: list = field(default_factory=list)


class DiffEngine:

    def compare(self, actual: str, expected: str) -> StructuralDiff:
        diff = StructuralDiff()

        actual_lines = actual.split("\n")
        expected_lines = expected.split("\n")

        matcher = difflib.SequenceMatcher(None, actual_lines, expected_lines)
        diff.similarity_ratio = matcher.ratio()

        unified = difflib.unified_diff(
            expected_lines, actual_lines,
            fromfile="expected", tofile="actual",
            lineterm=""
        )
        diff.unified_diff = "\n".join(unified)
        diff.total_diff_lines = sum(1 for l in unified if l.startswith("+") or l.startswith("-"))

        actual_headings = self._extract_headings(actual_lines)
        expected_headings = self._extract_headings(expected_lines)
        diff.heading_diffs = self._compare_heading_structures(actual_headings, expected_headings)

        actual_images = self._extract_images(actual)
        expected_images = self._extract_images(expected)
        diff.missing_images = [img for img in expected_images if img not in actual_images]
        diff.extra_images = [img for img in actual_images if img not in expected_images]

        actual_lists = self._extract_list_boundaries(actual_lines)
        expected_lists = self._extract_list_boundaries(expected_lines)
        diff.list_boundary_diffs = self._compare_lists(actual_lists, expected_lists)

        return diff

    def _extract_headings(self, lines: list[str]) -> list[HeadingNode]:
        headings = []
        for i, line in enumerate(lines):
            m = re.match(r"^(#{1,6})\s+(.+)$", line)
            if m:
                headings.append(HeadingNode(level=len(m.group(1)), text=m.group(2).strip(), line=i))
        return headings

    def _build_heading_tree(self, headings: list[HeadingNode]) -> list[HeadingNode]:
        root = []
        stack = []
        for h in headings:
            node = HeadingNode(level=h.level, text=h.text, line=h.line)
            while stack and stack[-1].level >= h.level:
                stack.pop()
            if stack:
                stack[-1].children.append(node)
            else:
                root.append(node)
            stack.append(node)
        return root

    def _compare_heading_structures(self, actual: list[HeadingNode], expected: list[HeadingNode]) -> list:
        diffs = []
        actual_dict = {(h.level, h.text): h for h in actual}
        expected_dict = {(h.level, h.text): h for h in expected}

        for key in expected_dict:
            if key not in actual_dict:
                diffs.append({"type": "missing_heading", "level": key[0], "text": key[1]})

        for key in actual_dict:
            if key not in expected_dict:
                diffs.append({"type": "extra_heading", "level": key[0], "text": key[1]})

        actual_tree = self._build_heading_tree(actual)
        expected_tree = self._build_heading_tree(expected)
        hierarchy_issues = self._validate_hierarchy(actual_tree, "h1", 0)
        diffs.extend(hierarchy_issues)

        return diffs

    def _validate_hierarchy(self, nodes: list[HeadingNode], parent_label, parent_line) -> list:
        issues = []
        for i, node in enumerate(nodes):
            expected_level = 1 if parent_label == "h1" else int(parent_label[1]) + 1
            if node.level > expected_level + 1:
                issues.append({
                    "type": "hierarchy_jump",
                    "from_level": expected_level,
                    "to_level": node.level,
                    "text": node.text,
                    "line": node.line,
                })
            issues.extend(self._validate_hierarchy(node.children, f"h{node.level}", node.line))
        return issues

    def _extract_images(self, markdown: str) -> list[dict]:
        images = []
        for m in re.finditer(r"!\[(.*?)\]\((.+?)\)", markdown):
            images.append({"alt": m.group(1), "src": m.group(2)})
        return images

    def _extract_list_boundaries(self, lines: list[str]) -> list[dict]:
        lists = []
        in_list = False
        start = 0
        list_type = None
        for i, line in enumerate(lines):
            stripped = line.strip()
            is_list_item = stripped.startswith("- ") or bool(re.match(r"^\d+[.)]\s", stripped))
            if is_list_item and not in_list:
                in_list = True
                start = i
                list_type = "unordered" if stripped.startswith("- ") else "ordered"
            elif not is_list_item and in_list:
                in_list = False
                lists.append({"start": start, "end": i - 1, "type": list_type, "length": i - start})
        if in_list:
            lists.append({"start": start, "end": len(lines) - 1, "type": list_type, "length": len(lines) - start})
        return lists

    def _compare_lists(self, actual: list[dict], expected: list[dict]) -> list:
        diffs = []
        if len(actual) != len(expected):
            diffs.append({
                "type": "list_count_mismatch",
                "actual": len(actual),
                "expected": len(expected),
            })
        for i, (a, e) in enumerate(zip(actual, expected)):
            if a["type"] != e["type"]:
                diffs.append({
                    "type": "list_type_mismatch",
                    "index": i,
                    "actual": a["type"],
                    "expected": e["type"],
                })
            if abs(a["length"] - e["length"]) > 2:
                diffs.append({
                    "type": "list_size_mismatch",
                    "index": i,
                    "actual": a["length"],
                    "expected": e["length"],
                })
        return diffs


def compute_structural_validity(markdown: str) -> dict:
    lines = markdown.split("\n")
    headings = [l for l in lines if l.startswith("#")]
    h1_count = sum(1 for l in headings if l.startswith("# "))
    issues = []

    if h1_count == 0:
        issues.append("missing_h1")
    if h1_count > 1:
        issues.append("multiple_h1")

    prev_level = 0
    for line in headings:
        level = len(line.split(" ")[0])
        if level > prev_level + 1 and prev_level > 0:
            issues.append(f"hierarchy_jump_{prev_level}_to_{level}")
        prev_level = level

    list_markers = set()
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("- "):
            list_markers.add("dash")
        elif re.match(r"^\d+\.\s", stripped):
            list_markers.add("numbered")

    consistency_issues = []
    # Real documents can legitimately have both unordered and ordered lists.
    # Therefore, mixing list styles is not a structural issue.

    score = 1.0
    if "missing_h1" in issues:
        score -= 0.2
    if "multiple_h1" in issues:
        score -= 0.15
    score -= len([i for i in issues if i.startswith("hierarchy_jump")]) * 0.1

    return {
        "score": max(0.0, score),
        "issues": issues,
        "h1_count": h1_count,
        "total_headings": len(headings),
        "list_consistency_issues": consistency_issues,
    }
