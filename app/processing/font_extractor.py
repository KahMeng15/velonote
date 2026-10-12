"""
Font-Aware PDF Text Extraction

Extracts text from PDF using pdfplumber's character-level data,
leveraging font name, size, color, bold/italic flags to determine
content structure (headings, body, lists, etc.)
"""

import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any

import pdfplumber

logger = logging.getLogger(__name__)


@dataclass
class FontStyle:
    """Represents a unique font style in the document."""

    name: str
    size: float
    is_bold: bool
    is_italic: bool
    color: tuple | None = None

    @property
    def key(self) -> str:
        return f"{self.name}|{self.size:.1f}|{self.is_bold}|{self.is_italic}"

    def __hash__(self):
        return hash(self.key)

    def __eq__(self, other):
        return isinstance(other, FontStyle) and self.key == other.key


@dataclass
class TextSpan:
    """A span of text with uniform font styling."""

    text: str
    font: FontStyle
    x0: float
    x1: float
    top: float
    bottom: float
    page: int


@dataclass
class TextLine:
    """A line of text composed of multiple spans."""

    spans: list[TextSpan] = field(default_factory=list)

    @property
    def text(self) -> str:
        if not self.spans:
            return ""
        parts = []
        for i, span in enumerate(self.spans):
            if i == 0:
                parts.append(span.text)
            else:
                prev = self.spans[i - 1]
                # Insert a space between spans if neither end has one
                if (
                    prev.text
                    and not prev.text[-1].isspace()
                    and span.text
                    and not span.text[0].isspace()
                ):
                    parts.append(" ")
                parts.append(span.text)
        return "".join(parts)

    @property
    def top(self) -> float:
        return min(s.top for s in self.spans) if self.spans else 0

    @property
    def bottom(self) -> float:
        return max(s.bottom for s in self.spans) if self.spans else 0

    @property
    def x0(self) -> float:
        return min(s.x0 for s in self.spans) if self.spans else 0

    @property
    def x1(self) -> float:
        return max(s.x1 for s in self.spans) if self.spans else 0

    @property
    def dominant_font(self) -> FontStyle | None:
        """Get the most common font in this line by character count."""
        if not self.spans:
            return None
        font_chars = Counter()
        for span in self.spans:
            font_chars[span.font] += len(span.text)
        return font_chars.most_common(1)[0][0]

    @property
    def max_font_size(self) -> float:
        if not self.spans:
            return 0
        return max(s.font.size for s in self.spans)

    @property
    def is_bold(self) -> bool:
        """True if dominant font is bold."""
        f = self.dominant_font
        return f.is_bold if f else False

    @property
    def page(self) -> int:
        return self.spans[0].page if self.spans else 0


@dataclass
class TextBlock:
    """A block of text (paragraph, heading, list item, etc.)"""

    lines: list[TextLine] = field(default_factory=list)
    block_type: str = "body"  # h1, h2, h3, h4, h5, body, list, ordered_list, table
    indent_level: int = 0

    @property
    def text(self) -> str:
        return " ".join(line.text.strip() for line in self.lines if line.text.strip())

    @property
    def top(self) -> float:
        return min(l.top for l in self.lines) if self.lines else 0

    @property
    def bottom(self) -> float:
        return max(l.bottom for l in self.lines) if self.lines else 0

    @property
    def x0(self) -> float:
        return min(l.x0 for l in self.lines) if self.lines else 0

    @property
    def dominant_font(self) -> FontStyle | None:
        if not self.lines:
            return None
        font_chars = Counter()
        for line in self.lines:
            for span in line.spans:
                font_chars[span.font] += len(span.text)
        return font_chars.most_common(1)[0][0] if font_chars else None

    @property
    def max_font_size(self) -> float:
        if not self.lines:
            return 0
        return max(l.max_font_size for l in self.lines)

    @property
    def page(self) -> int:
        return self.lines[0].page if self.lines else 0

    @property
    def has_bold(self) -> bool:
        return any(s.font.is_bold for l in self.lines for s in l.spans)

    @property
    def has_italic(self) -> bool:
        return any(s.font.is_italic for l in self.lines for s in l.spans)


class FontHierarchy:
    """
    Analyzes all fonts used in the document to build a hierarchy mapping
    font styles to heading levels.
    """

    def __init__(self):
        self.font_counts: Counter = Counter()  # FontStyle -> total char count
        self.body_font: FontStyle | None = None
        self.heading_map: dict[str, str] = {}  # font_key -> heading level

    def analyze(self, all_spans: list[TextSpan]):
        """Analyze all spans to determine font hierarchy."""
        # Count characters per font style
        for span in all_spans:
            text = span.text.strip()
            if text:
                self.font_counts[span.font] += len(text)

        if not self.font_counts:
            return

        # The most common font is the body font
        self.body_font = self.font_counts.most_common(1)[0][0]
        body_size = self.body_font.size

        # Collect unique font sizes (excluding body and very small/footer fonts)
        unique_sizes = set()
        for font_style, _count in self.font_counts.items():
            if font_style.size > body_size * 0.8:  # Ignore tiny text (footers, etc.)
                unique_sizes.add(font_style.size)

        # Sort sizes descending — larger fonts are higher-level headings
        sorted_sizes = sorted(unique_sizes, reverse=True)

        # Build heading map
        # Sizes larger than body get heading levels
        heading_sizes = [s for s in sorted_sizes if s > body_size + 0.5]

        for i, size in enumerate(heading_sizes):
            level = min(i + 1, 5)  # h1 through h5
            # Map all fonts at this size to this heading level
            for font_style in self.font_counts:
                if abs(font_style.size - size) < 0.5:
                    self.heading_map[font_style.key] = f"h{level}"

        # Bold text at body size -> promote to sub-heading if it's a standalone line
        # (This is handled during block classification, not here)

        logger.info(
            f"Font hierarchy: body={self.body_font.name} {self.body_font.size}pt, "
            f"heading sizes={heading_sizes}, total fonts={len(self.font_counts)}"
        )

    def get_level(self, font: FontStyle) -> str | None:
        """Get the heading level for a font, or None if body text."""
        return self.heading_map.get(font.key)

    def is_body(self, font: FontStyle) -> bool:
        """Check if a font is the body font."""
        if not self.body_font:
            return True
        return abs(font.size - self.body_font.size) < 0.5 and not font.is_bold


class FontAwareExtractor:
    """
    Extracts structured content from PDF using character-level font data.
    """

    # Footer/header patterns to filter
    FOOTER_PATTERNS = [
        re.compile(r"©.*Cisco", re.IGNORECASE),
        re.compile(r"Cisco\s*(Confidential|Public)", re.IGNORECASE),
        re.compile(r"All rights reserved", re.IGNORECASE),
        re.compile(r"Cisco\s+and/or\s+its\s+affiliates", re.IGNORECASE),
    ]

    # Bullet characters (including dashes/hyphens used as bullets)
    BULLET_CHARS = set("•‣◦⁃∙‐‑–—►▪▸➤➢")
    DASH_BULLET_CHARS = set("-–—‐‑")  # Dashes that can serve as list markers
    NUMBERED_PATTERN = re.compile(r"^(\d+[\.\)]\s)")

    # Headings to skip (video slides, etc.)
    SKIP_HEADING_PATTERNS = [
        re.compile(r"^Video\s*[-–—]\s*", re.IGNORECASE),
        re.compile(r"^Lab\s*[-–—]\s*", re.IGNORECASE),
    ]

    # Monospace font keywords for code detection
    MONO_FONT_KEYWORDS = (
        "mono", "courier", "consolas", "lucida console", "inconsolata",
        "source code", "fira code", "jetbrains",
    )

    # Code detection keywords
    CODE_KEYWORDS = (
        "public", "private", "class", "void", "static", "System.out",
        "println", "import", "def", "return", "function", "const", "let",
        "var", "int ", "float ", "double ", "boolean ", "char ", "String",
        "new ", "extends", "implements", "interface", "package",
        "@Override", "@SuppressWarnings",
    )

    def __init__(self):
        self.hierarchy = FontHierarchy()

    def extract(
        self, pdf_path: str, table_bboxes_per_page: dict[int, list] | None = None
    ) -> list[dict[str, Any]]:
        """
        Extract structured content from a PDF.

        Args:
            pdf_path: Path to the PDF file
            table_bboxes_per_page: Optional dict of {page_num: [bbox, ...]} for table regions to exclude

        Returns a list of page results, each containing blocks with
        type, text, font info, and position data.
        """
        all_spans = []
        page_data = []

        with pdfplumber.open(pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages):
                # Get table bboxes for this page to exclude
                exclude_bboxes = []
                if table_bboxes_per_page and (page_num + 1) in table_bboxes_per_page:
                    exclude_bboxes = table_bboxes_per_page[page_num + 1]

                page_spans = self._extract_page_spans(page, page_num + 1, exclude_bboxes)
                all_spans.extend(page_spans)
                page_data.append(
                    {
                        "page": page_num + 1,
                        "width": page.width,
                        "height": page.height,
                        "spans": page_spans,
                    }
                )

        # Build font hierarchy from all spans
        self.hierarchy.analyze(all_spans)

        # Process each page into blocks
        results = []
        for pd in page_data:
            lines = self._spans_to_lines(pd["spans"], pd["width"])
            lines = self._filter_headers_footers(lines, pd["height"])
            blocks = self._lines_to_blocks(lines, pd["width"])
            self._classify_blocks(blocks)
            results.append(
                {"page": pd["page"], "blocks": blocks, "width": pd["width"], "height": pd["height"]}
            )

        return results

    def _extract_page_spans(
        self, page, page_num: int, exclude_bboxes: list | None = None
    ) -> list[TextSpan]:
        """Extract TextSpans from a pdfplumber page using char data."""
        chars = page.chars
        if not chars:
            return []

        spans = []
        current_chars = []
        current_font = None

        for char in chars:
            # Skip chars inside excluded regions (e.g., table bboxes)
            if exclude_bboxes:
                char_x = char.get("x0", 0)
                char_y = char.get("top", 0)
                in_excluded = False
                for bbox in exclude_bboxes:
                    if (
                        bbox[0] - 5 <= char_x <= bbox[2] + 5
                        and bbox[1] - 5 <= char_y <= bbox[3] + 5
                    ):
                        in_excluded = True
                        break
                if in_excluded:
                    continue

            font_name = char.get("fontname", "")
            font_size = float(char.get("size", 12))

            # Detect bold/italic from font name
            name_lower = font_name.lower()
            is_bold = any(w in name_lower for w in ["bold", "black", "heavy", "demi"])
            is_italic = any(w in name_lower for w in ["italic", "oblique", "slant"])

            # Extract color
            color = None
            if "non_stroking_color" in char:
                c = char["non_stroking_color"]
                if isinstance(c, (list, tuple)) and len(c) >= 3:
                    color = tuple(c[:3])

            font = FontStyle(
                name=font_name, size=font_size, is_bold=is_bold, is_italic=is_italic, color=color
            )

            char.get("text", "")

            if current_font is None:
                current_font = font
                current_chars = [char]
            elif (
                font == current_font
                and current_chars
                and abs(char["top"] - current_chars[-1]["top"]) < 3
                and char["x0"] - current_chars[-1]["x1"] < 15
            ):
                # Same font, same line, reasonable gap → extend span
                # If there's a visible word gap (> 25% of font size), insert a space
                gap = char["x0"] - current_chars[-1]["x1"]
                if gap > font_size * 0.25 and current_chars:
                    last_text = current_chars[-1].get("text", "")
                    if last_text and not last_text[-1].isspace():
                        # Synthesise a space char by injecting it into the text
                        space_char = dict(current_chars[-1])  # shallow copy
                        space_char["text"] = " "
                        space_char["x0"] = current_chars[-1]["x1"]
                        space_char["x1"] = char["x0"]
                        current_chars.append(space_char)
                current_chars.append(char)
            else:
                # Different font or big gap → finalize current span
                if current_chars:
                    # If this split is due to a word gap (not just font change),
                    # ensure trailing space so the next span doesn't merge with this one
                    if (
                        font == current_font
                        and abs(char.get("top", 0) - current_chars[-1].get("top", 0)) < 3
                    ):
                        last_text = current_chars[-1].get("text", "")
                        if last_text and not last_text[-1].isspace():
                            space_char = dict(current_chars[-1])
                            space_char["text"] = " "
                            space_char["x0"] = current_chars[-1]["x1"]
                            space_char["x1"] = char["x0"]
                            current_chars.append(space_char)
                    span = self._finalize_span(current_chars, current_font, page_num)
                    if span:
                        spans.append(span)
                current_font = font
                current_chars = [char]

        # Finalize last span
        if current_chars and current_font:
            span = self._finalize_span(current_chars, current_font, page_num)
            if span:
                spans.append(span)

        return spans

    def _finalize_span(self, chars: list[dict], font: FontStyle, page_num: int) -> TextSpan | None:
        """Create a TextSpan from accumulated characters."""
        text = "".join(c.get("text", "") for c in chars)
        if not text.strip():
            # Even if blank, include spaces for gap tracking
            if not text:
                return None

        return TextSpan(
            text=text,
            font=font,
            x0=min(c["x0"] for c in chars),
            x1=max(c["x1"] for c in chars),
            top=min(c["top"] for c in chars),
            bottom=max(c["bottom"] for c in chars),
            page=page_num,
        )

    def _detect_columns(self, spans: list[TextSpan], page_width: float) -> list[list[TextSpan]]:
        """
        Detect if the page has a multi-column layout and split spans by column.
        Uses two strategies: bullet clustering (for bullet lists) and gap-based
        detection (for text columns). Returns column span groups (left-to-right).
        """
        if not spans or page_width < 100:
            return [spans] if spans else []

        content_spans = [s for s in spans if s.text.strip()]
        if len(content_spans) < 4:
            return [spans]

        # Strategy 1: Bullet x-position clustering
        result = self._detect_columns_by_bullets(spans, content_spans, page_width)
        if result is not None:
            return result

        # Strategy 2: Gap-based detection
        return self._detect_columns_by_gaps(spans, content_spans, page_width)

    def _detect_columns_by_bullets(self, all_spans, content_spans, page_width):
        """Detect columns by clustering bullet character x-positions."""
        bullet_x_positions = []
        for s in content_spans:
            text = s.text.strip()
            if text and text[0] in self.BULLET_CHARS:
                bullet_x_positions.append(s.x0)

        if len(bullet_x_positions) < 6:
            return None

        # Cluster bullet x0 positions (group within 20pt)
        sorted_positions = sorted(bullet_x_positions)
        clusters = [[sorted_positions[0]]]
        for x in sorted_positions[1:]:
            if x - clusters[-1][-1] < 20:
                clusters[-1].append(x)
            else:
                clusters.append([x])

        # Need ≥2 clusters with ≥3 bullets each, ≥50pt apart
        sig_clusters = [c for c in clusters if len(c) >= 3]
        if len(sig_clusters) < 2:
            return None

        centers = sorted(sum(c) / len(c) for c in sig_clusters)
        for i in range(1, len(centers)):
            if centers[i] - centers[i - 1] < 50:
                return None

        logger.debug(
            f"Bullet clustering: {len(centers)} columns at x={[f'{x:.0f}' for x in centers]}"
        )

        # Build boundaries as midpoints between cluster centers
        boundaries = [0]
        for i in range(1, len(centers)):
            boundaries.append((centers[i - 1] + centers[i]) / 2)
        boundaries.append(page_width)

        # Split spans by x0 position
        n = len(boundaries) - 1
        columns = [[] for _ in range(n)]
        for s in all_spans:
            for ci in range(n):
                if boundaries[ci] <= s.x0 < boundaries[ci + 1]:
                    columns[ci].append(s)
                    break
            else:
                # Assign to nearest column center
                best = min(range(len(centers)), key=lambda i: abs(s.x0 - centers[i]))
                columns[best].append(s)

        columns = [c for c in columns if c]
        if len(columns) > 1:
            logger.debug(
                f"Bullet-based {len(columns)}-col split: spans={[len(c) for c in columns]}"
            )
            return columns
        return None

    def _detect_columns_by_gaps(self, all_spans, content_spans, page_width):
        """Detect columns by finding horizontal gaps with no text coverage."""
        resolution = int(page_width) + 1
        coverage = [0] * resolution
        for s in content_spans:
            for x in range(max(0, int(s.x0)), min(resolution - 1, int(s.x1)) + 1):
                coverage[x] += 1

        text_left = next((i for i in range(resolution) if coverage[i] > 0), 0)
        text_right = next(
            (i for i in range(resolution - 1, -1, -1) if coverage[i] > 0), resolution - 1
        )
        text_width = text_right - text_left
        if text_width < 100:
            return [all_spans]

        # Find significant gaps (≥15pt empty x-ranges)
        gaps, in_gap, gap_start = [], False, 0
        for x in range(text_left, text_right + 1):
            if coverage[x] == 0:
                if not in_gap:
                    in_gap, gap_start = True, x
            elif in_gap:
                gw = x - gap_start
                margin = text_width * 0.05
                if gw >= 15 and gap_start > text_left + margin and x < text_right - margin:
                    gaps.append((gap_start, x, gw))
                in_gap = False

        if not gaps:
            return [all_spans]

        gaps.sort(key=lambda g: g[0])
        boundaries = [text_left] + [(gs + ge) / 2 for gs, ge, _ in gaps] + [text_right + 1]
        n = len(boundaries) - 1

        # Validate: ≥3 rows with content in multiple columns
        y_bins = defaultdict(set)
        for s in content_spans:
            y_key = round(s.top / 8) * 8
            mid_x = (s.x0 + s.x1) / 2
            for ci in range(n):
                if boundaries[ci] <= mid_x < boundaries[ci + 1]:
                    y_bins[y_key].add(ci)
                    break
        if sum(1 for cols in y_bins.values() if len(cols) >= 2) < 3:
            return [all_spans]

        columns = [[] for _ in range(n)]
        for s in all_spans:
            mid_x = (s.x0 + s.x1) / 2
            for ci in range(n):
                if boundaries[ci] <= mid_x < boundaries[ci + 1]:
                    columns[ci].append(s)
                    break
            else:
                best = min(
                    range(n), key=lambda i: abs(mid_x - (boundaries[i] + boundaries[i + 1]) / 2)
                )
                columns[best].append(s)

        columns = [c for c in columns if c]
        if len(columns) > 1:
            logger.debug(
                f"Gap-based {len(columns)}-col split: "
                f"boundaries={[f'{b:.0f}' for b in boundaries]}, "
                f"spans={[len(c) for c in columns]}"
            )
            return columns
        return [all_spans]

    def _spans_to_lines(self, spans: list[TextSpan], page_width: float = 0) -> list[TextLine]:
        """Group spans into lines based on vertical position, with column detection."""
        if not spans:
            return []

        # Detect columns first
        columns = self._detect_columns(spans, page_width)

        all_lines = []
        if len(columns) > 1:
            # Multi-column: process each column independently.
            # Offset Y positions for later columns so they sort sequentially
            # (all of column 1, then all of column 2, etc.)
            # We use a large offset (page height) per column to guarantee ordering.
            page_height = max((s.bottom for s in spans), default=800)
            for col_idx, col_spans in enumerate(columns):
                if col_idx > 0:
                    y_offset = col_idx * page_height
                    for s in col_spans:
                        s.top += y_offset
                        s.bottom += y_offset
                lines = self._column_spans_to_lines(col_spans)
                all_lines.extend(lines)
        else:
            # Single column: no offset needed
            all_lines = self._column_spans_to_lines(columns[0])

        return all_lines

    def _column_spans_to_lines(self, spans: list[TextSpan]) -> list[TextLine]:
        """Group spans within a single column into lines."""
        if not spans:
            return []

        # Sort by Y, then X
        spans.sort(key=lambda s: (round(s.top, 1), s.x0))

        lines = []
        current_line = TextLine(spans=[spans[0]])

        for span in spans[1:]:
            prev_span = current_line.spans[-1]

            # Check if same line (overlapping Y or close enough)
            prev_center = (prev_span.top + prev_span.bottom) / 2
            curr_center = (span.top + span.bottom) / 2

            if abs(prev_center - curr_center) < max(span.font.size * 0.6, 4):
                # Same line
                gap = span.x0 - prev_span.x1
                # Add space if there's a gap between words
                if gap > span.font.size * 0.15 and not prev_span.text.endswith(" "):
                    prev_span.text += " "
                current_line.spans.append(span)
            else:
                # New line
                if current_line.spans:
                    lines.append(current_line)
                current_line = TextLine(spans=[span])

        if current_line.spans:
            lines.append(current_line)

        return lines

    def _filter_headers_footers(self, lines: list[TextLine], page_height: float) -> list[TextLine]:
        """Remove page headers and footers."""
        header_cutoff = page_height * 0.05
        footer_cutoff = page_height * 0.90

        filtered = []
        for line in lines:
            text = line.text.strip()

            # Filter by position
            if line.bottom < header_cutoff or line.top > footer_cutoff:
                # Check if it's actually content (some slides have content near edges)
                if any(p.search(text) for p in self.FOOTER_PATTERNS):
                    continue
                if len(text) < 5:
                    continue

            # Filter by content
            if any(p.search(text) for p in self.FOOTER_PATTERNS):
                continue

            # Filter standalone page numbers
            if re.match(r"^\d{1,3}$", text.strip()):
                continue

            filtered.append(line)

        return filtered

    def _lines_to_blocks(self, lines: list[TextLine], page_width: float) -> list[TextBlock]:
        """
        Group lines into blocks (paragraphs) based on spacing and font.
        """
        if not lines:
            return []

        # Calculate page margins
        if lines:
            all_x0 = [l.x0 for l in lines]
            left_margin = min(all_x0) if all_x0 else 0
        else:
            left_margin = 0

        blocks = []
        current_block = TextBlock(lines=[lines[0]])

        for i in range(1, len(lines)):
            line = lines[i]
            prev_line = current_block.lines[-1]

            # Vertical gap between lines
            gap = line.top - prev_line.bottom

            # Font change?
            prev_font = prev_line.dominant_font
            curr_font = line.dominant_font

            font_changed = False
            if prev_font and curr_font:
                font_changed = (
                    abs(prev_font.size - curr_font.size) > 0.5
                    or prev_font.is_bold != curr_font.is_bold
                )

            # Significant indent change?
            indent_diff = abs(line.x0 - prev_line.x0)
            significant_indent = indent_diff > 15

            # Should we start a new block?
            should_split = False

            # Large vertical gap → new block
            avg_line_height = prev_line.bottom - prev_line.top
            if gap > avg_line_height * 1.5:
                should_split = True

            # Font changed → new block (or moderate gap + bold change)
            if font_changed:
                should_split = True
            elif gap > avg_line_height * 0.8 and prev_font and curr_font:
                # Moderate gap with any font difference → split
                if prev_font.key != curr_font.key:
                    should_split = True

            # Bullet or numbered item → new block
            line_text = line.text.strip()
            if line_text and (
                line_text[0] in self.BULLET_CHARS or self.NUMBERED_PATTERN.match(line_text)
            ):
                should_split = True

            # Significant indent change → new block
            if significant_indent and gap > 2:
                should_split = True

            if should_split:
                if current_block.lines:
                    blocks.append(current_block)
                current_block = TextBlock(lines=[line])
                # Track indentation
                if line.x0 > left_margin + 15:
                    current_block.indent_level = 1
                if line.x0 > left_margin + 35:
                    current_block.indent_level = 2
            else:
                current_block.lines.append(line)

        if current_block.lines:
            blocks.append(current_block)

        return blocks

    def _classify_blocks(self, blocks: list[TextBlock]):
        """
        Classify each block's type using font hierarchy and content patterns.
        """
        for block in blocks:
            text = block.text.strip()
            if not text:
                continue

            font = block.dominant_font
            if not font:
                block.block_type = "body"
                continue

            # Check font hierarchy for heading level
            heading_level = self.hierarchy.get_level(font)
            if heading_level and len(text) < 200:
                # Check if heading should be skipped (e.g., Video slides)
                if any(p.search(text) for p in self.SKIP_HEADING_PATTERNS):
                    block.block_type = "skip"
                else:
                    block.block_type = heading_level
                continue

            # Bold text at body-ish size, short and standalone → sub-heading
            if (
                font.is_bold
                and not self.hierarchy.is_body(font)
                and len(text) < 100
                and len(block.lines) <= 2
            ):
                # Check if this looks like a heading to skip
                if any(p.search(text) for p in self.SKIP_HEADING_PATTERNS):
                    block.block_type = "skip"
                    continue
                # Determine level based on size relative to body
                if self.hierarchy.body_font:
                    size_diff = font.size - self.hierarchy.body_font.size
                    if size_diff > 4:
                        block.block_type = "h2"
                    elif size_diff > 1:
                        block.block_type = "h3"
                    else:
                        block.block_type = "h4"
                else:
                    block.block_type = "h3"
                continue

            # Bold at body size, short → h4/h5
            if font.is_bold and len(text) < 80 and len(block.lines) == 1:
                block.block_type = "h4"
                continue

            # Check for bullet/list items
            first_char = text[0] if text else ""
            if first_char in self.BULLET_CHARS:
                block.block_type = "list"
                continue

            # Check for dash-prefixed list items (e.g., "-This is a point")
            if first_char in self.DASH_BULLET_CHARS and len(text) > 2:
                # Make sure it's not a negative number or hyphenated word
                rest = text[1:].lstrip()
                if rest and rest[0].isupper():
                    block.block_type = "list"
                    continue

            if self.NUMBERED_PATTERN.match(text):
                block.block_type = "ordered_list"
                continue

                    # Check for monospace fonts (code)
            if font and self._is_monospace(font.name):
                block.block_type = "code"
                continue

            # Check for code-like content using heuristics
            if len(text) > 15 and self._looks_like_code(text):
                block.block_type = "code"
                continue

            # Indented text: only classify as list if it has bullet-like characteristics
            if block.indent_level > 0:
                # Check if it looks like a continuation of previous block (body text)
                if text[0].islower() or len(text) > 120:
                    block.block_type = "body"
                else:
                    block.block_type = "body"  # Default indented to body, not list
                continue

            # Default: body
            block.block_type = "body"

    def _is_monospace(self, font_name: str) -> bool:
        name_lower = (font_name or "").lower()
        return any(kw in name_lower for kw in self.MONO_FONT_KEYWORDS)

    def _looks_like_code(self, text: str) -> bool:
        if not text or len(text) < 10 or len(text) > 500:
            return False
        has_brackets = "(" in text and ")" in text
        has_braces = "{" in text and "}" in text
        has_semicolon = ";" in text
        has_assignment = "=" in text and not text.startswith("=")
        if (has_braces and has_semicolon) or (has_brackets and has_semicolon and has_assignment):
            return True
        kw_count = sum(1 for kw in self.CODE_KEYWORDS if kw in text)
        syntax_score = sum([has_brackets, has_braces, has_semicolon, has_assignment])
        return kw_count >= 2 and syntax_score >= 2


def extract_font_aware(pdf_path: str) -> list[dict[str, Any]]:
    """Convenience function to extract structured content from PDF."""
    extractor = FontAwareExtractor()
    return extractor.extract(pdf_path)
