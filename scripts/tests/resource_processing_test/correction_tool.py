#!/usr/bin/env python3
"""
Correction CLI Tool — Interactive feedback for processing output.

Loads an extracted markdown file, lets the user annotate corrections
(promote/demote headings, mark lists, fix images, correct OCR errors),
and saves corrections as structured JSON test cases.

Usage:
  python correction_tool.py path/to/extracted_output.md
  python correction_tool.py path/to/extracted_output.md --expected path/to/correct.md
  python correction_tool.py --report path/to/report.json
  python correction_tool.py --analyze
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


class CorrectionSession:
    """Interactive correction session for processing output."""

    def __init__(self, output_path: str, expected_path: str = ""):
        self.output_path = output_path
        self.expected_path = expected_path
        self.corrections = []
        self.source_file = self._infer_source_file(output_path)

        with open(output_path) as f:
            self.content = f.read()
        self.lines = self.content.split("\n")

        self.expected_content = ""
        if expected_path and os.path.exists(expected_path):
            with open(expected_path) as f:
                self.expected_content = f.read()

    def _infer_source_file(self, output_path: str) -> str:
        base = os.path.basename(output_path)
        base = re.sub(r"^OUTPUT_", "", base)
        base = re.sub(r"_smart\.md$", "", base)
        base = re.sub(r"\.md$", "", base)
        return base

    def run_interactive(self):
        print(f"\nCorrection Session: {os.path.basename(self.output_path)}")
        print(f"Source file: {self.source_file}")
        print(f"Lines: {len(self.lines)}")
        print()

        if self.expected_content:
            self._show_diff()

        while True:
            try:
                cmd = input(">> ").strip()
                if not cmd:
                    continue
                if cmd == "exit" or cmd == "q":
                    break
                elif cmd == "save":
                    self._save()
                elif cmd == "diff":
                    self._show_diff()
                elif cmd.startswith("promote "):
                    self._promote(cmd)
                elif cmd.startswith("demote "):
                    self._demote(cmd)
                elif cmd.startswith("mark-body "):
                    self._mark_body(cmd)
                elif cmd.startswith("mark-heading "):
                    self._mark_heading(cmd)
                elif cmd.startswith("mark-list "):
                    self._mark_list(cmd)
                elif cmd.startswith("mark-olist "):
                    self._mark_olist(cmd)
                elif cmd == "fix-numbering":
                    self._fix_numbering()
                elif cmd == "fix-bullets":
                    self._fix_bullets()
                elif cmd.startswith("ignore-image "):
                    self._ignore_image(cmd)
                elif cmd.startswith("include-image "):
                    self._include_image(cmd)
                elif cmd.startswith("move-image "):
                    self._move_image(cmd)
                elif cmd.startswith("caption-image "):
                    self._caption_image(cmd)
                elif cmd.startswith("fix-ocr "):
                    self._fix_ocr(cmd)
                elif cmd.startswith("line "):
                    self._show_line(cmd)
                elif cmd == "help" or cmd == "h":
                    self._show_help()
                else:
                    print(f"Unknown command: {cmd}. Type 'help' for commands.")
            except EOFError:
                break
            except KeyboardInterrupt:
                print("\nUse 'save' to save or 'q' to quit without saving.")
                continue

    def _show_help(self):
        print("""
Commands:
  promote N              Promote heading at line N (H3→H2, H2→H1)
  demote N               Demote heading at line N
  mark-body N            Change heading/list at line N to body text
  mark-heading N <level> Change line N to specific heading level (1-6)
  mark-list N            Change body at line N to list item
  mark-olist N           Change to ordered list
  fix-numbering          Normalize all ordered lists
  fix-bullets            Normalize all list markers to '-'
  ignore-image <path>    Mark image as decorative
  include-image <path>   Mark image as important
  move-image <p> after <text>  Reposition image
  caption-image <p> <text>     Set image alt text
  fix-ocr N "correction" Correct OCR transcription at line N
  line N                 Show line N content
  diff                   Show side-by-side diff
  save                   Save corrections to file
  exit / q               Quit without saving
  help / h               Show this help
""")

    def _get_line_num(self, cmd: str) -> int:
        parts = cmd.split()
        if len(parts) >= 2:
            try:
                return int(parts[1])
            except ValueError:
                pass
        return 0

    def _get_text_after(self, cmd: str, keyword: str) -> str:
        idx = cmd.find(keyword)
        if idx >= 0:
            return cmd[idx + len(keyword):].strip().strip('"').strip("'")
        return ""

    def _show_line(self, cmd: str):
        n = self._get_line_num(cmd)
        if 0 < n <= len(self.lines):
            print(f"  L{n}: {self.lines[n - 1]}")
        else:
            print(f"Line {n} out of range (1-{len(self.lines)})")

    def _show_diff(self):
        if not self.expected_content:
            print("No expected content provided. Use --expected <file>")
            return
        import difflib
        expected_lines = self.expected_content.split("\n")
        actual_lines = self.content.split("\n")
        diff = difflib.unified_diff(expected_lines, actual_lines,
                                     fromfile="expected", tofile="actual", lineterm="")
        for line in diff:
            if line.startswith("+") or line.startswith("-") or line.startswith("@"):
                print(line)

    def _promote(self, cmd: str):
        n = self._get_line_num(cmd)
        if not n:
            return
        line = self.lines[n - 1] if 0 < n <= len(self.lines) else ""
        m = re.match(r"^(#+)\s", line)
        if m:
            current = len(m.group(1))
            if current > 1:
                self.corrections.append({
                    "type": "heading_level", "line": n,
                    "from": f"h{current}", "to": f"h{current - 1}",
                    "text": line.strip()[:60],
                })
                print(f"Promoted L{n} from h{current} to h{current - 1}")
            else:
                print("H1 cannot be promoted further")
        else:
            print(f"L{n} is not a heading")

    def _demote(self, cmd: str):
        n = self._get_line_num(cmd)
        if not n:
            return
        line = self.lines[n - 1] if 0 < n <= len(self.lines) else ""
        m = re.match(r"^(#+)\s", line)
        if m:
            current = len(m.group(1))
            if current < 6:
                self.corrections.append({
                    "type": "heading_level", "line": n,
                    "from": f"h{current}", "to": f"h{current + 1}",
                    "text": line.strip()[:60],
                })
                print(f"Demoted L{n} from h{current} to h{current + 1}")
            else:
                print("H6 cannot be demoted further")
        else:
            print(f"L{n} is not a heading")

    def _mark_body(self, cmd: str):
        n = self._get_line_num(cmd)
        if not n:
            return
        line = self.lines[n - 1] if 0 < n <= len(self.lines) else ""
        m = re.match(r"^(#+|-\s|\d+[.)]\s)", line)
        if m:
            self.corrections.append({
                "type": "mark_body", "line": n,
                "from": m.group(1).strip(),
                "text": line.strip()[:60],
            })
            print(f"Marked L{n} as body text")

    def _mark_heading(self, cmd: str):
        parts = cmd.split()
        if len(parts) < 3:
            print("Usage: mark-heading N <level>")
            return
        try:
            n = int(parts[1])
            level = int(parts[2])
            if 1 <= level <= 6:
                self.corrections.append({
                    "type": "mark_heading", "line": n, "to_level": level,
                    "text": (self.lines[n - 1] if 0 < n <= len(self.lines) else "").strip()[:60],
                })
                print(f"Marked L{n} as h{level}")
            else:
                print("Level must be 1-6")
        except ValueError:
            print("Invalid line or level")

    def _mark_list(self, cmd: str):
        n = self._get_line_num(cmd)
        if not n:
            return
        self.corrections.append({
            "type": "mark_list", "line": n,
            "text": (self.lines[n - 1] if 0 < n <= len(self.lines) else "").strip()[:60],
        })
        print(f"Marked L{n} as list item")

    def _mark_olist(self, cmd: str):
        n = self._get_line_num(cmd)
        if not n:
            return
        self.corrections.append({
            "type": "mark_olist", "line": n,
            "text": (self.lines[n - 1] if 0 < n <= len(self.lines) else "").strip()[:60],
        })
        print(f"Marked L{n} as ordered list item")

    def _fix_numbering(self):
        self.corrections.append({"type": "fix_numbering", "scope": "document"})
        print("Normalize numbering recorded")

    def _fix_bullets(self):
        self.corrections.append({"type": "fix_bullets", "scope": "document"})
        print("Normalize bullets recorded")

    def _ignore_image(self, cmd: str):
        img_path = self._get_text_after(cmd, "ignore-image ")
        if img_path:
            self.corrections.append({
                "type": "ignore_image", "image_path": img_path, "reason": "decorative",
            })
            print(f"Image '{img_path}' marked as decorative")

    def _include_image(self, cmd: str):
        img_path = self._get_text_after(cmd, "include-image ")
        if img_path:
            self.corrections.append({
                "type": "include_image", "image_path": img_path, "reason": "important",
            })
            print(f"Image '{img_path}' marked as important")

    def _move_image(self, cmd: str):
        parts = cmd.split()
        if "after" in parts:
            after_idx = parts.index("after")
            img_path = " ".join(parts[1:after_idx])
            anchor = " ".join(parts[after_idx + 1:]).strip('"').strip("'")
            self.corrections.append({
                "type": "move_image", "image_path": img_path, "anchor_text": anchor,
            })
            print(f"Image '{img_path}' to be placed after '{anchor}'")

    def _caption_image(self, cmd: str):
        rest = cmd[len("caption-image "):].strip()
        if " " in rest:
            img_path, caption = rest.split(" ", 1)
            self.corrections.append({
                "type": "caption_image", "image_path": img_path.strip(),
                "caption": caption.strip('"').strip("'"),
            })
            print(f"Image '{img_path}' caption set")

    def _fix_ocr(self, cmd: str):
        parts = cmd.split(maxsplit=2)
        if len(parts) >= 3:
            try:
                n = int(parts[1])
                correction = parts[2].strip('"').strip("'")
                original = self.lines[n - 1] if 0 < n <= len(self.lines) else ""
                self.corrections.append({
                    "type": "ocr_correction", "line": n,
                    "from": original.strip()[:60],
                    "to": correction,
                })
                print(f"OCR fix applied at L{n}: '{original.strip()[:40]}' -> '{correction[:40]}'")
            except ValueError:
                print("Invalid line number")

    def _save(self):
        correction_file = self._get_correction_path()
        data = {
            "source_file": self.source_file,
            "output_file": self.output_path,
            "expected_file": self.expected_path or "",
            "timestamp": datetime.utcnow().isoformat(),
            "corrections": self.corrections,
            "correct_content": self.expected_content if self.expected_content else "",
        }
        os.makedirs(os.path.dirname(correction_file), exist_ok=True)
        with open(correction_file, "w") as f:
            json.dump(data, f, indent=2)
        print(f"Saved {len(self.corrections)} corrections to {correction_file}")

    def _get_correction_path(self) -> str:
        base_dir = Path(__file__).parent / "corrections"
        base_dir.mkdir(exist_ok=True)
        return str(base_dir / f"{Path(self.source_file).stem}_corrections.json")

    def batch_corrections(self, corrections_dir: str):
        corrections_list = []
        for f in Path(corrections_dir).glob("*.json"):
            try:
                with open(f) as fh:
                    data = json.load(fh)
                    corrections_list.append(data)
            except Exception:
                continue
        return corrections_list


def analyze_corrections(corrections_dir: str):
    """Analyze accumulated corrections and print insights."""
    corrections = []
    for f in Path(corrections_dir).glob("*.json"):
        try:
            with open(f) as fh:
                data = json.load(fh)
                corrections.append(data)
        except Exception as e:
            print(f"  Error reading {f}: {e}")

    if not corrections:
        print("No corrections found")
        return

    type_counts = {}
    for c in corrections:
        for corr in c.get("corrections", []):
            t = corr.get("type", "unknown")
            type_counts[t] = type_counts.get(t, 0) + 1

    total = sum(type_counts.values())
    print(f"\nCorrection Analysis")
    print(f"{'─' * 50}")
    print(f"Total correction files: {len(corrections)}")
    print(f"Total individual corrections: {total}")
    print()
    print(f"{'Type':<25} {'Count':<8} {'%':<8}")
    print(f"{'─' * 41}")
    for t, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        pct = (count / total) * 100
        print(f"{t:<25} {count:<8} {pct:.1f}%")


def main():
    parser = argparse.ArgumentParser(description="Correction CLI Tool")
    parser.add_argument("input", nargs="?", help="Extracted markdown file to correct")
    parser.add_argument("--expected", "-e", help="Expected/correct markdown for comparison")
    parser.add_argument("--report", "-r", help="JSON report to extract corrections from")
    parser.add_argument("--analyze", action="store_true", help="Analyze all accumulated corrections")
    args = parser.parse_args()

    if args.analyze:
        corrections_dir = Path(__file__).parent / "corrections"
        analyze_corrections(str(corrections_dir))
        return

    if args.report:
        with open(args.report) as f:
            report = json.load(f)
        for file_result in report.get("files", []):
            if file_result.get("warnings") or file_result.get("diff", {}).get("similarity_ratio", 1) < 0.9:
                output_path = file_result.get("file", "")
                if output_path:
                    session = CorrectionSession(str(Path(__file__).parent / "output" / "reports" / f"OUTPUT_{Path(output_path).stem}.md"))
                    session.run_interactive()
        return

    if not args.input:
        parser.print_help()
        return

    session = CorrectionSession(args.input, args.expected or "")
    session.run_interactive()


if __name__ == "__main__":
    main()
