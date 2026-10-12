"""
Signal Merger

Merges signals from multiple extraction methods (font-aware, AI layout, tables)
into a unified, clean Markdown document.
"""

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class MergedBlock:
    """A unified content block with merged signals."""

    text: str
    block_type: str  # h1, h2, h3, h4, h5, body, list, ordered_list, table
    y_position: float
    page: int
    confidence: float = 1.0
    indent_level: int = 0
    has_bold_spans: bool = False
    has_italic_spans: bool = False
    font_size: float = 0.0
    markdown_overrides: str | None = None  # Pre-formatted markdown (for tables)
    inline_formats: list[dict] = field(default_factory=list)  # [{start, end, style}]


class SignalMerger:
    """
    Merges signals from font-aware extraction, AI layout detection,
    and table detection into a single unified document.
    """

    # Mapping from layout detector labels to block types
    LAYOUT_TO_TYPE = {
        "Title": "h1",
        "Section-header": "h2",
        "Text": "body",
        "List-item": "list",
        "Table": "table",
        "Caption": "caption",
        "Footnote": "footnote",
        "Page-footer": "skip",
        "Page-header": "skip",
        "Formula": "body",
        "Picture": "skip",
    }

    # Pattern for ordered lists like "(i)", "1)", "(a)", "a)"
    ORDERED_LIST_RE = re.compile(r"^(?:\()?([0-9a-zA-Z]|[ivxIVX]+)(?:\.|\))(?:\s+|$)")

    # Pattern for numbered topic headings like "1.1", "1.2", "2.3.1"
    NUMBERED_HEADING_RE = re.compile(r"^(\d+(?:\.\d+)+)\s+(.+)$")

    # Pattern for module/chapter-level headings
    MODULE_HEADING_RE = re.compile(r"^(?:Module|Chapter|Unit)\s+\d+", re.IGNORECASE)

    def merge(
        self,
        font_blocks: list[dict[str, Any]],
        layout_detections: list[dict[str, Any]] | None = None,
        tables: list[dict[str, Any]] | None = None,
    ) -> list[MergedBlock]:
        """
        Merge all extraction signals into a unified list of blocks.
        """
        all_blocks = []

        for page_data in font_blocks:
            page_num = page_data["page"]
            page_width = page_data["width"]
            page_height = page_data["height"]
            blocks = page_data["blocks"]

            # Get layout detections for this page
            page_layouts = None
            if layout_detections and page_num - 1 < len(layout_detections):
                page_layouts = layout_detections[page_num - 1]

            # Get tables for this page
            page_tables = None
            if tables and page_num - 1 < len(tables):
                page_tables = tables[page_num - 1]

            # Process font blocks
            for block in blocks:
                text = block.text.strip()
                if not text:
                    continue

                merged = MergedBlock(
                    text=text,
                    block_type=block.block_type,
                    y_position=block.top,
                    page=page_num,
                    indent_level=block.indent_level,
                    has_bold_spans=block.has_bold,
                    has_italic_spans=block.has_italic,
                    font_size=block.max_font_size,
                )

                # Enhance with layout detection signal
                if page_layouts:
                    layout_type = self._match_layout(block, page_layouts, page_width, page_height)
                    if layout_type:
                        merged = self._resolve_conflict(merged, layout_type)

                all_blocks.append(merged)

            # Insert tables at their Y-positions
            if page_tables:
                for table in page_tables:
                    table_block = MergedBlock(
                        text="",
                        block_type="table",
                        y_position=table["y_position"],
                        page=page_num,
                        markdown_overrides=table["markdown"],
                    )
                    all_blocks.append(table_block)

        # Sort by page, then Y position
        all_blocks.sort(key=lambda b: (b.page, b.y_position))

        # Post-processing passes (order matters!)
        all_blocks = self._remove_duplicates(all_blocks)
        all_blocks = self._normalize_heading_hierarchy(all_blocks)
        all_blocks = self._split_inline_bullets(all_blocks)
        all_blocks = self._clean_list_formatting(all_blocks)
        all_blocks = self._merge_continuations(all_blocks)
        all_blocks = self._fix_list_wrapping(all_blocks)
        all_blocks = self._clean_list_formatting(all_blocks)  # Second pass: clean up after merging
        all_blocks = self._promote_orphan_body_in_lists(all_blocks)
        all_blocks = self._split_embedded_list_headers(all_blocks)
        all_blocks = self._remove_redundant_metadata(all_blocks)
        all_blocks = self._split_examples(all_blocks)
        all_blocks = self._extract_list_headers(all_blocks)

        return all_blocks

    def _match_layout(
        self,
        block,
        detections: list[dict],
        page_width: float,
        page_height: float,
    ) -> str | None:
        """Match a font block to a layout detection by position overlap."""
        if not detections:
            return None

        block_center_y = (block.top + block.bottom) / 2
        block_center_x = (block.x0 + (block.x1 if hasattr(block, "x1") else block.x0 + 100)) / 2

        best_match = None
        best_overlap = 0

        for det in detections:
            bbox = det["bbox"]
            img_w = det.get("image_width", page_width)
            img_h = det.get("image_height", page_height)

            scale_x = page_width / img_w
            scale_y = page_height / img_h

            lx1 = bbox[0] * scale_x
            ly1 = bbox[1] * scale_y
            lx2 = bbox[2] * scale_x
            ly2 = bbox[3] * scale_y

            if lx1 <= block_center_x <= lx2 and ly1 <= block_center_y <= ly2:
                area = (lx2 - lx1) * (ly2 - ly1)
                conf = det.get("confidence", 0.5)
                score = conf / max(area, 1)

                if score > best_overlap:
                    best_overlap = score
                    best_match = det

        if best_match:
            label = best_match["label"]
            return self.LAYOUT_TO_TYPE.get(label)

        return None

    def _resolve_conflict(self, merged: MergedBlock, layout_type: str) -> MergedBlock:
        """
        Resolve conflicts between font-based and layout-based classification.
        Font data is primary (most reliable), layout is confirmation/tiebreaker.
        """
        font_type = merged.block_type

        if layout_type == "skip":
            if font_type in ("body",):
                merged.block_type = "skip"
            return merged

        if font_type.startswith("h") and layout_type.startswith("h"):
            merged.confidence = 0.95
            return merged

        if font_type == "body" and layout_type.startswith("h"):
            if len(merged.text) < 100:
                merged.block_type = layout_type
                merged.confidence = 0.7
            return merged

        if font_type.startswith("h") and layout_type == "body":
            if len(merged.text) > 150:
                merged.block_type = "body"
                merged.confidence = 0.8
            return merged

        if layout_type == "list" and font_type == "body":
            merged.block_type = "list"
            merged.confidence = 0.75
            return merged

        return merged

    # ─── Post-processing passes ──────────────────────────────────────

    def _remove_duplicates(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Remove duplicate content blocks.
        Enhanced: fuzzy-match headings across levels, detect recurring slide titles.
        """
        cleaned = []
        seen_headers = {}  # normalized_text -> block_type
        seen_all_blocks = set()

        for block in blocks:
            if block.block_type == "skip":
                continue

            text_norm = block.text.strip().lower()

            # Global deduplication for every block (prevent exact repeating institutional lines)
            if len(text_norm) > 10 and text_norm in seen_all_blocks:
                # If it's a heading, we definitely remove it.
                # If it's body text, we remove it if it's identical and short.
                if block.block_type.startswith("h") or len(text_norm) < 200:
                    logger.debug(f"Removing exact duplicate block: {block.text[:60]}")
                    continue
            seen_all_blocks.add(text_norm)

            if block.block_type.startswith("h"):
                # Normalize for comparison
                norm = re.sub(r"\s*\(cont\.?(?:inued)?\).*$", "", block.text, flags=re.IGNORECASE)
                norm = norm.strip().lower()
                # Remove leading numbering for comparison
                norm_no_num = re.sub(r"^\d+(?:\.\d+)*\s*", "", norm).strip()

                # Check exact normalized duplicate
                if norm in seen_headers:
                    logger.debug(f"Removing duplicate header: {block.text}")
                    continue

                # Check if this heading text (without numbering) is a substring of an already-seen heading
                is_duplicate = False
                for seen_text, _seen_type in list(seen_headers.items()):
                    seen_no_num = re.sub(r"^\d+(?:\.\d+)*\s*", "", seen_text).strip()
                    if len(norm_no_num) < 4 or len(seen_no_num) < 4:
                        continue

                    # If either is a close substring of the other, it's a duplicate
                    if norm_no_num == seen_no_num or (
                        len(norm_no_num) > 10
                        and (norm_no_num in seen_no_num or seen_no_num in norm_no_num)
                    ):
                        # Keep the more specific one
                        if len(norm) >= len(seen_text):
                            cleaned = [
                                b
                                for b in cleaned
                                if not (
                                    b.block_type.startswith("h")
                                    and b.text.strip().lower() == seen_text
                                )
                            ]
                            seen_headers.pop(seen_text, None)
                        else:
                            is_duplicate = True
                            break

                if is_duplicate:
                    logger.debug(f"Removing fuzzy-duplicate header: {block.text}")
                    continue

                seen_headers[norm] = block.block_type

            cleaned.append(block)

        return cleaned

    def _normalize_heading_hierarchy(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Normalize heading levels based on font size ranks and document patterns.
        Fixes the issue where many slides are flat H5 or otherwise mis-mapped.
        """
        # Pass 1: Collect all distinct font sizes used for headings
        heading_sizes = set()
        for block in blocks:
            if block.block_type.startswith("h") and block.font_size > 0:
                heading_sizes.add(round(block.font_size, 1))

        # Rank them descending (largest = rank 1)
        sorted_sizes = sorted(heading_sizes, reverse=True)
        size_to_level = {size: (f"h{i + 1}" if i < 3 else "body") for i, size in enumerate(sorted_sizes)}

        # Pass 2: Apply semantic overrides and size-based levels
        for block in blocks:
            if not block.block_type.startswith("h"):
                continue

            text = block.text.strip()

            # Rule 0: Demote long text (headings are rarely long paragraphs)
            if len(text) > 160:
                block.block_type = "body"
                continue

            # Rule 1: High-priority semantic overrides (Module/numbered topics)
            if self.MODULE_HEADING_RE.match(text):
                block.block_type = "h1"
                continue

            m = self.NUMBERED_HEADING_RE.match(text)
            if m:
                num_parts = m.group(1).split(".")
                if len(num_parts) == 2:
                    block.block_type = "h2"
                elif len(num_parts) >= 3:
                    block.block_type = "h3"
                continue

            # Rule 2: Fallback to font-size ranking
            rounded_size = round(block.font_size, 1)
            if rounded_size in size_to_level:
                block.block_type = size_to_level[rounded_size]

        # Pass 3: Fix hierarchy jumps (no jumping from h1 to h4)
        last_level = 0
        for block in blocks:
            if block.block_type.startswith("h"):
                try:
                    level = int(block.block_type[1])
                    if level > last_level + 1 and last_level > 0:
                        corrected = last_level + 1
                        block.block_type = f"h{corrected}"
                        level = corrected
                    last_level = level
                except (ValueError, IndexError):
                    continue

        # Pass 4: Enforce ONLY ONE H1 (the document title).
        seen_first_h1 = False
        for block in blocks:
            if block.block_type == "h1":
                if seen_first_h1:
                    block.block_type = "h2"
                else:
                    seen_first_h1 = True

        if not seen_first_h1:
            for block in blocks:
                if block.block_type.startswith("h"):
                    block.block_type = "h1"
                    break
        # Pass 5: Remove consecutive duplicate/empty headers
        final_blocks = []
        for block in blocks:
            if not final_blocks:
                final_blocks.append(block)
                continue

            last = final_blocks[-1]
            if block.block_type.startswith("h") and last.block_type.startswith("h"):
                # If they have identical text, remove the second
                if block.text.strip().lower() == last.text.strip().lower():
                    logger.debug(f"Removing consecutive identical header: {block.text}")
                    continue
                # If the first is empty or low quality, and levels are similar, favor the second
                if len(last.text) < 3 and block.block_type == last.block_type:
                    final_blocks.pop()
                    final_blocks.append(block)
                    continue

            final_blocks.append(block)

        return final_blocks

    def _split_inline_bullets(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Split blocks that contain multiple inline bullet characters (•) into
        separate list items.
        """
        BULLET_CHARS = "•‣◦⁃∙►▪▸➤➢"
        BULLET_PATTERN = re.compile(r"[" + re.escape(BULLET_CHARS) + r"]")

        result = []

        for block in blocks:
            text = block.text.strip()

            bullet_count = sum(1 for c in text if c in BULLET_CHARS)

            if bullet_count < 2:
                if bullet_count == 1 and text:
                    if text[0] in BULLET_CHARS:
                        block.block_type = "list"
                    else:
                        block.text = BULLET_PATTERN.sub("", block.text).strip()
                result.append(block)
                continue

            normalized = text
            for bc in BULLET_CHARS:
                normalized = normalized.replace(bc, "\x00")

            parts = normalized.split("\x00")
            items = []
            for part in parts:
                cleaned = part.strip()
                if cleaned and len(cleaned) > 1:
                    items.append(cleaned)

            if not items:
                result.append(block)
                continue

            for item_text in items:
                new_block = MergedBlock(
                    text=item_text,
                    block_type="list",
                    y_position=block.y_position,
                    page=block.page,
                    confidence=block.confidence,
                    indent_level=block.indent_level,
                )
                result.append(new_block)

        return result

    def _clean_list_formatting(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Clean up list item formatting:
        1. Fix double-dashes (e.g., "- -Transmission" → "Transmission")
        2. Fix missing space after dash ("-This" → "This" — the dash prefix is added by markdown formatter)
        3. Detect leading dash/hyphen as list indicator
        4. Fix dash stuck to text (e.g., "-This" → "- This" in body text)
        """
        DASH_CHARS = set("-–—‐‑")

        for block in blocks:
            text = block.text.strip()
            if not text:
                continue

            # Detect ordered list markers
            m_ordered = self.ORDERED_LIST_RE.match(text)
            if m_ordered:
                # Strip the marker and mark as ordered_list
                # We keep the marker for context during merging but eventually the formatter handles numbering
                block.block_type = "ordered_list"

            # Detect leading dash as list marker
            elif text[0] in DASH_CHARS and len(text) > 1:
                # Strip leading dash(es) and mark as list
                cleaned = text.lstrip("-–—‐‑ ")
                if cleaned:
                    block.text = cleaned
                    if block.block_type == "body":
                        block.block_type = "list"

            # Fix double-dash patterns within text
            # e.g. "- -Transmission is achieved by..." → "Transmission is achieved by..."
            if block.block_type in ("list", "ordered_list"):
                text = block.text
                # Remove leading dashes/hyphens (the markdown formatter adds "- " itself)
                text = re.sub(r"^[\-–—‐‑]+\s*", "", text)
                block.text = text.strip()

            # Fix dash stuck to text in body blocks (e.g., "-This is created" → "This is created")
            # This handles cases from interleaved multi-column PDF text
            if block.block_type == "body":
                text = block.text
                # Fix ": -Text" → ": Text" (dash following punctuation)
                text = re.sub(r"([:\.])\s*-([A-Z])", r"\1 \2", text)
                block.text = text

        return blocks

    def _merge_continuations(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Merge sentence fragments that were split across lines/blocks.
        Enhanced: more aggressive merging for mid-sentence breaks.
        """
        if not blocks:
            return blocks

        BULLET_CHARS = set("•‣◦⁃∙►▪▸➤➢")
        # Words that indicate a sentence is continuing
        CONNECTOR_WORDS = {
            "and",
            "or",
            "the",
            "of",
            "with",
            "to",
            "in",
            "a",
            "an",
            "for",
            "from",
            "by",
            "on",
            "at",
            "as",
            "is",
            "are",
            "was",
            "were",
            "be",
            "been",
            "being",
            "that",
            "which",
            "such",
            "including",
            "like",
            "than",
            "into",
        }

        merged = [blocks[0]]

        for block in blocks[1:]:
            prev = merged[-1]

            # Skip merging tables, code blocks, or headings
            if block.block_type in ("table", "code") or prev.block_type in ("table", "code"):
                merged.append(block)
                continue

            if block.block_type.startswith("h") or prev.block_type.startswith("h"):
                merged.append(block)
                continue

            # Never merge blocks with bullet characters
            block_has_bullets = any(c in BULLET_CHARS for c in block.text)
            prev_has_bullets = any(c in BULLET_CHARS for c in prev.text)
            if block_has_bullets or prev_has_bullets:
                merged.append(block)
                continue

            should_merge = False
            text = block.text.strip()
            prev_text = prev.text.strip()

            if not text or not prev_text:
                merged.append(block)
                continue

            # Same page check
            same_page = block.page == prev.page

            # --- Body + Body merging ---
            if prev.block_type == "body" and block.block_type == "body" and same_page:
                # Current starts with lowercase → definite continuation
                if text[0].islower():
                    should_merge = True
                # Previous doesn't end with sentence-terminating punctuation
                # and Current is either lowercase OR a common "continuation" fragment
                elif prev_text[-1] not in ".!?:\"')":
                    # If prev ends in a comma or connector, it's almost certainly a split line
                    last_word = prev_text.split()[-1].lower().rstrip(".,;:")
                    if last_word in CONNECTOR_WORDS or prev_text[-1] in ",:;":
                        should_merge = True
                    # If next is short and uppercase, it might be a split phrase (e.g., "Masyar- \n Akat")
                    elif len(text.split()) < 3:
                        should_merge = True
                    # If prev has no punctuation at all in the last 10 chars, it's likely a mid-sentence slide wrap
                    elif not any(c in ".!?" for c in prev_text[-10:]):
                        should_merge = True

            # --- List + Body merging (stray text after list items) ---
            if (
                prev.block_type in ("list", "ordered_list")
                and block.block_type == "body"
                and same_page
            ):
                # Current starts with lowercase → continuation of list item
                if text[0].islower():
                    should_merge = True
                # Parenthetical continuation
                elif text[0] == "(":
                    should_merge = True
                # Previous list item ends with connector word
                elif text:
                    last_word = prev_text.split()[-1].lower().rstrip(",")
                    if last_word in CONNECTOR_WORDS:
                        should_merge = True
                # Previous doesn't end with sentence-ending punctuation
                # and text starts with common continuation words
                if prev_text[-1] not in ".!?:\"'":
                    first_word = text.split()[0].lower() if text.split() else ""
                    if first_word in CONNECTOR_WORDS or text[0].islower():
                        should_merge = True

            # --- Body + Body merging for indented continuations ---
            if (
                prev.block_type == "body"
                and block.block_type == "body"
                and same_page
                and block.indent_level > 0
            ):
                # Indented body that starts with lowercase → continuation
                if text[0].islower():
                    should_merge = True
                # Previous doesn't end with sentence-ending punctuation
                if prev_text[-1] not in ".!?:\"'":
                    should_merge = True

            # --- List + List with indent (sub-item continuation) ---
            if (
                prev.block_type in ("list", "ordered_list")
                and block.block_type in ("list", "ordered_list")
                and same_page
            ):
                # If the current "list" item starts with lowercase → continuation
                # BUT: skip if both items are short (likely separate terms from bullet splitting)
                prev_is_short = len(prev_text) < 40
                curr_is_short = len(text) < 40
                if text[0].islower() and not (prev_is_short and curr_is_short):
                    should_merge = True

            # --- List + Body that doesn't end in sentence-ending punctuation ---
            if (
                prev.block_type in ("list", "ordered_list")
                and block.block_type == "body"
                and same_page
            ):
                # If previous list item doesn't end with sentence punctuation, merge
                if prev_text[-1] not in ".!?:;" and text[0].islower():
                    should_merge = True
                # If text is very short and starts lowercase, likely continuation
                if len(text) < 80 and text[0].islower():
                    should_merge = True
                # Parenthetical or abbreviation continuation (e.g., "PDAs,", "(SOHO)")
                if text[0] == "(" or (
                    prev_text[-1] not in ".!?"
                    and text[0].isupper()
                    and len(text.split()[0]) <= 5
                    and text.split()[0][-1] in ",)."
                ):
                    should_merge = True

            if should_merge:
                sep = " "
                if prev.text.endswith("-") or prev.text.endswith("–") or prev.text.endswith("—"):
                    # Check if it was a hyphenated word or just a dash
                    # If it ends with a letter-dash, it's likely a hyphenated word split by line
                    if len(prev.text) > 2 and prev.text[-2].isalpha():
                        sep = ""
                        prev.text = prev.text[:-1]

                prev.text += sep + block.text
            else:
                merged.append(block)

        return merged

    def _promote_orphan_body_in_lists(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Promote body blocks to list items when sandwiched between list items.
        """
        if len(blocks) < 3:
            return blocks

        for i in range(1, len(blocks) - 1):
            block = blocks[i]
            prev = blocks[i - 1]
            nxt = blocks[i + 1]
            if (
                block.block_type == "body"
                and prev.block_type in ("list", "ordered_list")
                and nxt.block_type in ("list", "ordered_list")
                and block.page == prev.page
                and len(block.text) < 100
            ):
                block.block_type = prev.block_type

        return blocks

    def _fix_list_wrapping(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Fix list items that were split mid-sentence across multiple blocks.
        If a list item's text doesn't end with sentence-ending punctuation,
        and the next block (list or body) starts with lowercase, merge them.
        """
        if not blocks:
            return blocks

        merged = [blocks[0]]

        for block in blocks[1:]:
            prev = merged[-1]

            # Only fix list items on the same page
            if (
                prev.block_type in ("list", "ordered_list")
                and block.block_type in ("list", "ordered_list", "body")
                and prev.page == block.page
            ):
                prev_text = prev.text.strip()
                curr_text = block.text.strip()

                if prev_text and curr_text:
                    # If previous doesn't end with sentence punctuation
                    # and current starts with lowercase → merge
                    prev_ends_sentence = prev_text[-1] in ".!?:"
                    curr_starts_lower = curr_text[0].islower()

                    # Merge if previous doesn't end sentence and current starts lowercase
                    # BUT: skip if both items are short (likely separate terms from bullet splitting)
                    prev_is_short = len(prev_text) < 40
                    curr_is_short = len(curr_text) < 40
                    # Merge if previous doesn't end sentence and current starts lowercase
                    # OR if previous doesn't end in terminal punctuation and current is a short fragment (Phase 4)
                    if (not prev_ends_sentence and curr_starts_lower) or (
                        prev_text[-1] not in ".!?" and len(curr_text.split()) < 5
                    ):
                        # Merge if they are not both short terms
                        prev_is_short = len(prev_text) < 40
                        curr_is_short = len(curr_text) < 40
                        if not (prev_is_short and curr_is_short):
                            sep = " "
                            if prev.text.endswith("-"):
                                sep = ""
                                prev.text = prev.text[:-1]
                            prev.text += sep + block.text
                            continue

                    # Merge if previous has unclosed parenthesis
                    # e.g., "Mobile devices (such as smart phones, tablets," + "PDAs, and...)"
                    if prev_text.count("(") > prev_text.count(")"):
                        prev.text += " " + block.text
                        continue

            merged.append(block)

        return merged

    def _split_embedded_list_headers(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Split list items that contain embedded list header labels.
        E.g., "...sharing printers Disadvantages of P2P:" → split into two blocks.
        """
        LABEL_PATTERN = re.compile(
            r"^(.+?)\s+((?:Advantages|Disadvantages|Features|Benefits|Drawbacks|"
            r"Characteristics|Properties|Types|Examples|Steps|Requirements)"
            r"\s+(?:of\s+)?[^:]*:\s*)$",
            re.IGNORECASE,
        )

        result = []
        for block in blocks:
            if block.block_type not in ("list", "ordered_list"):
                result.append(block)
                continue

            text = block.text.strip()
            m = LABEL_PATTERN.match(text)
            if m:
                list_text = m.group(1).strip()
                header_text = m.group(2).strip()

                # Only split if the list text before the header is meaningful
                if len(list_text) > 5:
                    # Keep the list item with just the first part
                    block.text = list_text
                    result.append(block)

                    # Add the header label as a bold body block
                    header_block = MergedBlock(
                        text=f"**{header_text}**",
                        block_type="body",
                        y_position=block.y_position,
                        page=block.page,
                        confidence=block.confidence,
                    )
                    result.append(header_block)
                    continue

            result.append(block)

        return result

    def _remove_redundant_metadata(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Remove redundant metadata lines:
        - "Module Title: X ... Module Objective: Y" → "**Objective:** Y"
        - Clean standalone "Module Objective:" to "**Objective:**"
        - Remove repeated "Module N" headings after the first
        """
        # Find the first h1 title
        h1_title = None
        for block in blocks:
            if block.block_type == "h1":
                h1_title = block.text.strip().lower()
                break

        # Track if we've seen a module-level heading already
        seen_module_heading = False
        seen_first_h1 = False

        cleaned = []
        for block in blocks:
            text = block.text.strip()

            if block.block_type == "h1" and not seen_first_h1:
                seen_first_h1 = True
                cleaned.append(block)
                continue

            # Handle combined "Module Title: X Module Objective: Y" lines
            # Match "Module Title: X" or "Module Title: X Module Objective: Y"
            if re.match(r"^(?:\*\*)?Module\s+Title", text, re.IGNORECASE):
                # Extract objective if present in the same line
                obj_match = re.search(r"(?:Module\s+)?Objective:\s*(.+)$", text, re.IGNORECASE)
                if obj_match:
                    obj_text = obj_match.group(1).strip()
                    block.text = f"**Objective:** {obj_text}"
                    cleaned.append(block)
                else:
                    logger.debug(f"Removing redundant metadata: {text[:60]}")
                continue

            # Clean standalone "Module Objective:" → "**Objective:**"
            if re.match(r"^Module\s+Objective:\s*", text, re.IGNORECASE):
                block.text = re.sub(
                    r"^Module\s+Objective:", "**Objective:**", text, flags=re.IGNORECASE
                )
                cleaned.append(block)
                continue

            # Remove repeated institutional headers (Phase 4)
            # e.g., course names or professor names appearing on every slide
            lowered = text.lower()
            if h1_title and h1_title in lowered and len(text) < len(h1_title) + 15:
                # Basic safety check to ensure it's not a newly introduced section
                if len(cleaned) > 0 and (
                    cleaned[-1].text.lower() == text.lower() or text.count(" ") < 4
                ):
                    logger.debug(f"Removing repeated title header/footer: {text}")
                    continue

            # Remove repeated "Module N" headings (e.g., "Module 1 – New Terms")
            if block.block_type.startswith("h"):
                module_match = re.match(r"^(?:Module|Chapter|Unit)\s+\d+", text, re.IGNORECASE)
                if module_match:
                    if seen_module_heading:
                        # Demote to h3 or keep but remove "Module N" prefix
                        # Actually, check if it's something like "Module 1 – New Terms and Commands"
                        # In that case, just use "New Terms and Commands" as h3
                        dash_match = re.match(r"^Module\s+\d+\s*[–—\-]\s*(.+)", text, re.IGNORECASE)
                        if dash_match:
                            block.text = dash_match.group(1).strip()
                            block.block_type = "h3"
                        else:
                            logger.debug(f"Removing repeated module heading: {text}")
                            continue
                    else:
                        seen_module_heading = True

            cleaned.append(block)

        return cleaned

    def _split_examples(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Split blocks that contain multiple examples on one line into separate lines.
        E.g., "Capital letter: A = 01000001 Number: 9 = 00111001 Special character: # = 00100011"
        → three separate paragraphs.
        """
        # Pattern: "Label: value = bits  Label: value = bits"
        EXAMPLE_PATTERN = re.compile(r"(?:^|\s)([A-Z][a-z]+(?:\s+[a-z]+)*\s*:\s*\S+\s*=\s*[01]+)")

        result = []
        for block in blocks:
            if block.block_type != "body":
                result.append(block)
                continue

            text = block.text.strip()
            matches = list(EXAMPLE_PATTERN.finditer(text))

            if len(matches) >= 2:
                # Extract all examples
                examples = []
                for m in matches:
                    examples.append(m.group(1).strip())

                if len(examples) >= 2:
                    # Get any prefix text before the first example
                    prefix_end = matches[0].start()
                    prefix = text[:prefix_end].strip()

                    if prefix:
                        prefix_block = MergedBlock(
                            text=prefix,
                            block_type="body",
                            y_position=block.y_position,
                            page=block.page,
                            confidence=block.confidence,
                        )
                        result.append(prefix_block)

                    for ex in examples:
                        # Bold the label part
                        parts = ex.split(":", 1)
                        if len(parts) == 2:
                            formatted = f"**{parts[0].strip()}:** {parts[1].strip()}"
                        else:
                            formatted = ex
                        ex_block = MergedBlock(
                            text=formatted,
                            block_type="body",
                            y_position=block.y_position,
                            page=block.page,
                            confidence=block.confidence,
                        )
                        result.append(ex_block)
                    continue

            result.append(block)

        return result

    def _extract_list_headers(self, blocks: list[MergedBlock]) -> list[MergedBlock]:
        """
        Extract list header patterns from the end of body paragraphs.
        E.g., "...P2P network. Advantages of P2P:" → split into body + bold label
        Also: "Disadvantages of P2P:" at the start of a body block → bold label
        """
        # Pattern: text ending with "Label:" followed by list items
        LIST_HEADER_PATTERN = re.compile(
            r"^(.*?\.\s+)((?:Advantages|Disadvantages|Features|Benefits|Drawbacks|"
            r"Characteristics|Properties|Types|Examples|Steps|Requirements)\s+(?:of\s+)?[^:]{0,40}:\s*)$",
            re.IGNORECASE,
        )
        # Pattern for standalone list header at start
        STANDALONE_HEADER_PATTERN = re.compile(
            r"^((?:Advantages|Disadvantages|Features|Benefits|Drawbacks|"
            r"Characteristics|Properties|Types|Examples|Steps|Requirements)\s+(?:of\s+)?[^:]*:\s*)$",
            re.IGNORECASE,
        )

        result = []
        for i, block in enumerate(blocks):
            if block.block_type != "body":
                result.append(block)
                continue

            text = block.text.strip()

            # Check if body text ends with a list header pattern
            m = LIST_HEADER_PATTERN.match(text)
            if m:
                body_part = m.group(1).strip()
                header_part = m.group(2).strip()

                # Check if followed by list items
                has_list_after = i + 1 < len(blocks) and blocks[i + 1].block_type in (
                    "list",
                    "ordered_list",
                )

                if has_list_after and body_part:
                    # Split: body text + bold header
                    body_block = MergedBlock(
                        text=body_part,
                        block_type="body",
                        y_position=block.y_position,
                        page=block.page,
                        confidence=block.confidence,
                    )
                    result.append(body_block)

                    header_block = MergedBlock(
                        text=f"**{header_part}**",
                        block_type="body",
                        y_position=block.y_position,
                        page=block.page,
                        confidence=block.confidence,
                    )
                    result.append(header_block)
                    continue

            # Check if standalone list header
            sm = STANDALONE_HEADER_PATTERN.match(text)
            if sm:
                block.text = f"**{text}**"
                result.append(block)
                continue

            result.append(block)

        return result


def blocks_to_markdown(blocks: list[MergedBlock]) -> str:
    """
    Convert merged blocks to clean Markdown text.
    """
    lines = []
    prev_type = None
    in_list = False
    current_page = None

    for block in blocks:
        if block.block_type == "skip":
            continue

        text = block.text.strip()
        if not text and not block.markdown_overrides:
            continue

        if block.page != current_page:
            current_page = block.page
            if lines and lines[-1] != "":
                lines.append("")
            lines.append(f"<!-- Page {current_page} -->")
            lines.append("")

        # Close list if switching to non-list
        if in_list and block.block_type not in ("list", "ordered_list"):
            in_list = False
            lines.append("")  # Blank line after list

        # Headings
        if block.block_type.startswith("h"):
            level = int(block.block_type[1])
            prefix = "#" * level

            if lines:
                if lines[-1] != "":
                    lines.append("")

            heading_text = _clean_heading(text)
            lines.append(f"{prefix} {heading_text}")
            lines.append("")
            prev_type = block.block_type
            continue

        # Tables
        if block.block_type == "table":
            if block.markdown_overrides:
                if lines and lines[-1] != "":
                    lines.append("")
                lines.append(block.markdown_overrides)
                lines.append("")
            prev_type = "table"
            continue

        # List items
        if block.block_type in ("list", "ordered_list"):
            clean_text = _clean_list_item(text)

            if block.block_type == "list":
                prefix = "- "
            else:
                prefix = "1. "

            if not in_list:
                in_list = True

            # Cap indent level to prevent code-block rendering (max 1 level = 2 spaces)
            indent_level = min(block.indent_level, 1)
            indent = "  " * indent_level
            lines.append(f"{indent}{prefix}{clean_text}")
            prev_type = block.block_type
            continue

        # Code blocks
        if block.block_type == "code":
            if lines and lines[-1] != "":
                lines.append("")
            lang = "java" if any(kw in text for kw in ("public class", "public static void", "System.out", "String[] args", "import java")) else ""
            lines.append(f"```{lang}")
            lines.append(text)
            lines.append("```")
            lines.append("")
            prev_type = "code"
            continue

        # Body text
        if block.block_type == "body":
            if lines and prev_type and prev_type.startswith("h"):
                pass
            elif lines and lines[-1] != "":
                lines.append("")

            formatted = _apply_inline_formatting(text, block)
            lines.append(formatted)
            prev_type = "body"
            continue

        # Caption
        if block.block_type == "caption":
            lines.append(f"*{text}*")
            lines.append("")
            prev_type = "caption"
            continue

    # Clean up — collapse excessive blank lines, then escape unescaped <
    # characters ONLY outside fenced code blocks so React doesn't crash.
    result = "\n".join(lines)
    result = re.sub(r"\n{3,}", "\n\n", result)

    out_lines = []
    in_code_block = False
    for line in result.split("\n"):
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            out_lines.append(line)
            continue
        if not in_code_block:
            # Escape < to &lt; unless it's part of an HTML comment
            line = re.sub(r'<(?!!--)', r'&lt;', line)
        out_lines.append(line)
    result = "\n".join(out_lines)

    result = result.strip() + "\n"

    return result


def _clean_heading(text: str) -> str:
    """Clean heading text."""
    text = re.sub(r"\s*\(cont\.?(?:inued)?\).*$", "", text, flags=re.IGNORECASE)
    text = text.strip()
    return text


def _clean_list_item(text: str) -> str:
    """Clean list item text — remove bullet characters, dashes, and numbering."""
    # Remove leading bullet characters (but NOT asterisks used for bold markdown)
    text = re.sub(r"^[•‣◦⁃∙‐‑–—\-►▪▸➤➢]+\s*", "", text)
    # After removing bullets, also strip any remaining leading dashes
    text = re.sub(r"^[\-–—‐‑]+\s*", "", text)
    # Remove leading single asterisk bullet (but preserve ** for bold markdown)
    if text.startswith("* ") and not text.startswith("** "):
        text = text[2:]
    # Remove leading numbering if present
    text = re.sub(r"^\d+[\.\\)]\s*", "", text)
    # Remove any remaining leading whitespace
    return text.strip()


def _apply_inline_formatting(text: str, block: MergedBlock) -> str:
    """Apply bold/italic inline formatting to text."""
    # Only bold short term-definition patterns (term < 40 chars, total < 120 chars)
    # This prevents entire paragraphs from being bolded
    if len(text) > 120:
        return text
    match = re.match(r"^([A-Z][a-zA-Z0-9\s/()]+?)\s*[-–—:]\s+(.+)$", text)
    if match:
        term = match.group(1).strip()
        defn = match.group(2).strip()
        if len(term) < 40:
            return f"**{term}:** {defn}"

    return text
