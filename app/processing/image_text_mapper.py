"""
Maps extracted images to their nearest text blocks and inserts image references
into the markdown at the correct position.
"""

import logging
import re

logger = logging.getLogger(__name__)

DIAGRAM_REF_PATTERNS = [
    r"as\s+shown\s+in\s+(the\s+)?(figure|diagram|illustration|chart|image)",
    r"see\s+(figure|diagram|illustration|chart|image)",
    r"in\s+(figure|diagram|illustration|chart|image)\s*\d*",
    r"illustrated\s+(below|above|in)",
    r"(figure|fig\.?)\s*\d+",
    r"(diagram|chart|graph)\s*\d+",
    r"(below|above|following)\s+(figure|diagram|illustration)",
]


class ImageTextMapper:
    """Inserts image references into markdown at positions matching their source location."""

    PAGE_BAND_COUNT = 5

    def insert_images(self, markdown: str, images: list, source_format: str = "") -> str:
        if not images:
            return markdown

        source_images = [img for img in images if hasattr(img, "to_dict") or isinstance(img, dict)]
        if not source_images:
            return markdown

        if source_format == "pptx":
            return self._insert_pptx_images(markdown, source_images)
        elif source_format == "pdf":
            return self._insert_pdf_images(markdown, source_images)
        else:
            return self._insert_generic_images(markdown, source_images)

    def _insert_pptx_images(self, markdown: str, images: list) -> str:
        lines = markdown.split("\n")
        slide_boundaries = self._find_slide_boundaries(lines)
        images_by_slide = self._group_images_by_slide(images)

        result = []
        current_slide = 0
        slide_images_placed = set()
        all_placed = set()

        for line_idx, line in enumerate(lines):
            result.append(line)

            slide_num = self._detect_slide_number(line, line_idx, slide_boundaries)
            if slide_num:
                current_slide = slide_num
                slide_images_placed = set()

            if self._is_markdown_heading(line):
                heading_text = line.lstrip("# ").strip()
                slide_images = images_by_slide.get(current_slide, [])
                for img in slide_images:
                    img_id = img.get("id") if isinstance(img, dict) else getattr(img, "id", "")
                    if img_id in slide_images_placed:
                        continue
                    if self._text_matches_image(heading_text, img):
                        result.append(self._format_image_ref(img))
                        slide_images_placed.add(img_id)
                        all_placed.add(img_id)

            is_last_line = (line_idx == len(lines) - 1) or (
                line_idx < len(lines) - 1 and not lines[line_idx + 1].strip()
            )
            if is_last_line and current_slide > 0:
                slide_images = images_by_slide.get(current_slide, [])
                unplaced = [
                    img
                    for img in slide_images
                    if (img.get("id") if isinstance(img, dict) else getattr(img, "id", ""))
                    not in slide_images_placed
                ]
                for img in unplaced:
                    result.append(self._format_image_ref(img))
                    all_placed.add(img.get("id") if isinstance(img, dict) else getattr(img, "id", ""))

        # Ensure all images are placed even if no slides/headings were detected
        for s_num, s_images in images_by_slide.items():
            for img in s_images:
                img_id = img.get("id") if isinstance(img, dict) else getattr(img, "id", "")
                if img_id not in all_placed:
                    result.append(self._format_image_ref(img))
                    all_placed.add(img_id)

        return "\n".join(result)

    def _insert_pdf_images(self, markdown: str, images: list) -> str:
        lines = markdown.split("\n")
        images_by_page = self._group_images_by_page(images)

        result = []
        current_page = 0
        page_images_placed = set()
        all_placed = set()

        for line_idx, line in enumerate(lines):
            result.append(line)

            page_ref = self._detect_page_number(line)
            if page_ref:
                current_page = page_ref
                page_images_placed = set()

            has_ref_pattern = any(re.search(p, line.lower()) for p in DIAGRAM_REF_PATTERNS)
            if has_ref_pattern:
                page_images = images_by_page.get(current_page, [])
                unplaced = [
                    img
                    for img in page_images
                    if (img.get("id") if isinstance(img, dict) else getattr(img, "id", ""))
                    not in page_images_placed
                ]
                if unplaced:
                    result.append(self._format_image_ref(unplaced[0]))
                    img_id = unplaced[0].get("id") if isinstance(unplaced[0], dict) else getattr(unplaced[0], "id", "")
                    page_images_placed.add(img_id)
                    all_placed.add(img_id)

            is_page_end = self._is_page_boundary(line, lines, line_idx)
            if is_page_end and current_page > 0:
                page_images = images_by_page.get(current_page, [])
                unplaced = [
                    img
                    for img in page_images
                    if (img.get("id") if isinstance(img, dict) else getattr(img, "id", ""))
                    not in page_images_placed
                ]
                for img in unplaced:
                    result.append(self._format_image_ref(img))
                    img_id = img.get("id") if isinstance(img, dict) else getattr(img, "id", "")
                    all_placed.add(img_id)
                    page_images_placed.add(img_id)

        # Ensure all images are placed even if no pages were detected
        for p_num, p_images in images_by_page.items():
            for img in p_images:
                img_id = img.get("id") if isinstance(img, dict) else getattr(img, "id", "")
                if img_id not in all_placed:
                    result.append(self._format_image_ref(img))
                    all_placed.add(img_id)

        return "\n".join(result)

    def _insert_generic_images(self, markdown: str, images: list) -> str:
        lines = markdown.split("\n")
        images_sorted = sorted(
            images,
            key=lambda img: (
                img.get("position_y", 0) if isinstance(img, dict) else getattr(img, "position_y", 0)
            ),
        )

        result = []
        image_idx = 0
        placed = set()

        for line_idx, line in enumerate(lines):
            result.append(line)

            has_ref = any(re.search(p, line.lower()) for p in DIAGRAM_REF_PATTERNS)
            if has_ref and image_idx < len(images_sorted):
                img = images_sorted[image_idx]
                result.append(self._format_image_ref(img))
                placed.add(img.get("id") if isinstance(img, dict) else getattr(img, "id", ""))
                image_idx += 1

        while image_idx < len(images_sorted):
            img = images_sorted[image_idx]
            img_id = img.get("id") if isinstance(img, dict) else getattr(img, "id", "")
            if img_id not in placed:
                result.append(self._format_image_ref(img))
            image_idx += 1

        return "\n".join(result)

    def _format_image_ref(self, img) -> str:
        if isinstance(img, dict):
            path = img.get("file_path", "")
            caption = img.get("caption", "") or img.get("alt_text", "") or "Figure"
        else:
            path = getattr(img, "file_path", "")
            caption = getattr(img, "caption", "") or getattr(img, "alt_text", "") or "Figure"

        rel_path = self._to_relative_path(path) if path else ""
        return f"![{caption}]({rel_path})"

    def _to_relative_path(self, file_path: str) -> str:
        if not file_path:
            return ""
        from pathlib import Path
        path_obj = Path(file_path)
        filename = path_obj.name
        # The parent directory is the resource ID (e.g. rs_0c06969e)
        resource_id = path_obj.parent.name
        return f"/api/resources/{resource_id}/images/{filename}"

    def _find_slide_boundaries(self, lines: list[str]) -> list[int]:
        boundaries = []
        for i, line in enumerate(lines):
            if line.startswith("# ") or line.startswith("## Slide"):
                boundaries.append(i)
        return boundaries

    def _detect_slide_number(self, line: str, line_idx: int, boundaries: list[int]) -> int | None:
        m = re.match(r"<!--\s*Slide\s+(\d+)\s*-->", line)
        if m:
            return int(m.group(1))
        if line_idx in boundaries:
            for i, b in enumerate(boundaries):
                if b == line_idx:
                    return i + 1
        return None

    def _group_images_by_slide(self, images: list) -> dict[int, list]:
        groups = {}
        for img in images:
            slide = (
                img.get("slide_index", 0)
                if isinstance(img, dict)
                else getattr(img, "slide_index", 0)
            )
            if slide not in groups:
                groups[slide] = []
            groups[slide].append(img)
        return groups

    def _group_images_by_page(self, images: list) -> dict[int, list]:
        groups = {}
        for img in images:
            page = (
                img.get("page_number", 0)
                if isinstance(img, dict)
                else getattr(img, "page_number", 0)
            )
            if page not in groups:
                groups[page] = []
            groups[page].append(img)
        return groups

    def _detect_page_number(self, line: str) -> int | None:
        m = re.match(r"<!--\s*Page\s+(\d+)\s*-->", line)
        if m:
            return int(m.group(1))
        m = re.match(r"\[Page\s+(\d+)\]", line)
        if m:
            return int(m.group(1))
        return None

    def _is_markdown_heading(self, line: str) -> bool:
        return bool(re.match(r"^#{1,6}\s", line))

    def _text_matches_image(self, heading_text: str, img) -> bool:
        caption = img.get("caption", "") if isinstance(img, dict) else getattr(img, "caption", "")
        keywords = re.split(r"[\s,;:.-]+", caption.lower()) if caption else []
        heading_lower = heading_text.lower()
        return any(kw and len(kw) > 3 and kw in heading_lower for kw in keywords)

    def _is_page_boundary(self, line: str, all_lines: list[str], idx: int) -> bool:
        if idx >= len(all_lines) - 1:
            return True
        if idx < len(all_lines) - 1 and re.match(r"<!--\s*Page\s+\d+\s*-->", all_lines[idx + 1]):
            return True
        if line.strip() == "" and all_lines[idx + 1].startswith("# "):
            return True
        return False

    def insert_image_placeholders(
        self, markdown: str, images: list, source_format: str = ""
    ) -> str:
        result = markdown
        pattern_refs = set()
        for pattern in DIAGRAM_REF_PATTERNS:
            for m in re.finditer(pattern, result, re.IGNORECASE):
                line_start = result.rfind("\n", 0, m.start()) + 1
                line_end = result.find("\n", m.end())
                if line_end == -1:
                    line_end = len(result)
                pattern_refs.add((line_start, line_end))

        placed_ids = set()
        for img in images:
            img_id = img.get("id", "") if isinstance(img, dict) else getattr(img, "id", "")
            if img_id in placed_ids:
                continue
            img_ref = self._format_image_ref(img)

            for start, end in sorted(pattern_refs):
                if start < len(result):
                    insert_pos = end
                    result = result[:insert_pos] + "\n" + img_ref + result[insert_pos:]
                    placed_ids.add(img_id)
                    break

        if len(placed_ids) < len(images):
            result += "\n\n"
            for img in images:
                img_id = img.get("id", "") if isinstance(img, dict) else getattr(img, "id", "")
                if img_id not in placed_ids:
                    result += self._format_image_ref(img) + "\n"
                    placed_ids.add(img_id)

        return result
