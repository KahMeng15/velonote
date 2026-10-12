"""
Text processing module for cleaning, structuring, and formatting extracted OCR content.
Handles header detection, content cleanup, sentence joining, and structure analysis.
"""

import logging
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

logger = logging.getLogger(__name__)


class ContentType(StrEnum):
    """Content type classification"""

    H1 = "h1"  # Section header
    H2 = "h2"  # Topic header
    H3 = "h3"  # Subtopic header
    H4 = "h4"  # Subheading level 4
    H5 = "h5"  # Subheading level 5
    BODY = "body"  # Regular text
    CODE = "code"  # Code block
    LIST = "list"  # List item (bullet)
    ORDERED_LIST = "ordered_list"  # Numbered list
    TABLE_ROW = "table_row"  # Table row
    IMAGE = "image"  # Image
    NOTE_TITLE = "note_title"
    SUBJECT_NAME = "subject_name"
    GROUP_NAME = "group_name"


@dataclass
class ContentSegment:
    """Represents a content segment with metadata"""

    content: str
    content_type: ContentType
    page_number: int
    confidence: float = 0.9
    original_lines: list[str] = None
    metadata: dict[str, Any] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary"""
        return {
            "content": self.content,
            "type": self.content_type.value,
            "page": self.page_number,
            "confidence": self.confidence,
            "metadata": self.metadata or {},
        }


class HeaderDetector:
    """Detects and classifies headers using multiple strategies"""

    # Blacklist patterns for non-content
    BLACKLIST_PATTERNS = [
        r"^©.*$",  # Copyright
        r"^[©®™].*$",  # Symbols
        r"^\s*Page\s+\d+\s*$",  # Page numbers
        r"^\s*Slide\s+\d+\s*$",  # Slide numbers
        r"^\s*\d+\s*$",  # Standalone numbers
        r"^www\..+\.\w+$",  # URLs
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",  # Emails
        r"^(Confidential|Proprietary|Internal|Draft|Confidential Information)$",
        r"^(For Official Use|Restricted|Private|Classified)$",
    ]

    # Footer/Header patterns
    FOOTER_HEADER_PATTERNS = [
        r"^(Footer|Header):\s*",
        r"^\d+\s*$",  # Just page numbers
        r"^Page\s+\d+\s+of\s+\d+$",
        r"^www\..*$",
    ]

    # List item patterns
    LIST_PATTERNS = [
        r"^[\s]*[-•*]\s+",  # Bullet points
        r"^[\s]*\d+\.\s+",  # Numbered lists
        r"^[\s]*[a-z]\)\s+",  # Letter lists
    ]

    def __init__(self):
        self.blacklist_regex = [re.compile(p, re.IGNORECASE) for p in self.BLACKLIST_PATTERNS]
        self.footer_header_regex = [
            re.compile(p, re.IGNORECASE) for p in self.FOOTER_HEADER_PATTERNS
        ]
        self.list_regex = [re.compile(p) for p in self.LIST_PATTERNS]

    def is_blacklisted(self, text: str) -> bool:
        """Check if text matches blacklist patterns"""
        text = text.strip()
        if len(text) < 3:  # Too short
            return True

        for pattern in self.blacklist_regex:
            if pattern.match(text):
                logger.debug(f"Blacklisted: {text}")
                return True
        return False

    def is_footer_header(self, text: str) -> bool:
        """Check if text is footer/header content"""
        text = text.strip()
        for pattern in self.footer_header_regex:
            if pattern.match(text):
                return True
        return False

    def is_list_item(self, text: str) -> bool:
        """Check if text is a list item"""
        for pattern in self.list_regex:
            if pattern.match(text.strip()):
                return True
        return False

    def is_table_row(self, text: str) -> bool:
        """Check if text is a markdown table row"""
        text = text.strip()
        # Markdown table rows start with | and contain |
        if text.startswith("|") and text.count("|") >= 2:
            return True
        return False

    def detect_header_level(
        self,
        text: str,
        line_position: int,
        total_lines: int,
        avg_line_length: float,
        font_size: float | None = None,
    ) -> tuple[ContentType, float]:
        """
        Detect header level using multiple strategies
        Returns: (ContentType, confidence_score)
        """
        text = text.strip()

        # Check for table rows first (before headers/lists)
        if self.is_table_row(text):
            # Skip table separator rows (|---|---|)
            if re.match(r"^\s*\|\s*[-:]+\s*(\|\s*[-:]+\s*)*\|?\s*$", text):
                # It's a separator row, mark as TABLE_ROW with zero confidence (skip)
                return ContentType.TABLE_ROW, 0.0
            else:
                return ContentType.TABLE_ROW, 0.95

        # Strategy 1: Font size detection (if available)
        if font_size:
            if font_size >= 18:
                return ContentType.H1, 0.95
            elif font_size >= 14:
                return ContentType.H2, 0.90
            elif font_size >= 12:
                return ContentType.H3, 0.85

        # Strategy 2: Length-based (shorter lines = headers)
        text_length = len(text)
        if text_length < avg_line_length * 0.5:
            if text_length < avg_line_length * 0.3:
                return ContentType.H1, 0.85
            else:
                return ContentType.H2, 0.80

        # Strategy 3: Position-based (top of page = header)
        relative_position = line_position / max(total_lines, 1)
        if relative_position < 0.1 and text_length < avg_line_length * 0.6:
            return ContentType.H1, 0.80
        elif relative_position < 0.2 and text_length < avg_line_length * 0.7:
            return ContentType.H2, 0.75

        # Strategy 4: Pattern-based (all caps, numbered sections)
        if text.isupper() and len(text) > 3:
            if text_length < avg_line_length * 0.6:
                return ContentType.H1, 0.90
            else:
                return ContentType.H2, 0.80

        # Check for numbered sections
        section_match = re.match(r"^(\d+\.?\s+)?[A-Z][^.!?]*$", text)
        if section_match and text_length < avg_line_length * 0.7:
            return ContentType.H2, 0.75

        # Check for list items
        if self.is_list_item(text):
            return ContentType.LIST, 0.85

        # Default: body text
        return ContentType.BODY, 0.60


class TextCleaner:
    """Cleans and normalizes extracted text"""

    def __init__(self):
        self.header_detector = HeaderDetector()

    def clean_text(self, text: str, is_header: bool = False) -> str:
        """
        Clean text by removing artifacts and normalizing whitespace
        """
        # Remove common OCR artifacts
        text = re.sub(r"^[\s]*\|[\s]*$", "", text, flags=re.MULTILINE)  # Orphaned pipes
        text = re.sub(r"[\s]+", " ", text)  # Multiple spaces to single space
        text = text.strip()

        # Clean quotes and dashes
        text = text.replace(""", '"').replace(""", '"')
        text = text.replace("–", "-").replace("—", "-")

        return text

    def join_sentences(self, lines: list[str]) -> str:
        """
        Join multi-line sentences into single lines
        Uses punctuation and layout to determine sentence boundaries
        """
        if not lines:
            return ""

        joined = []
        current_sentence = ""

        for line in lines:
            line = line.strip()
            if not line:
                if current_sentence:
                    joined.append(current_sentence)
                    current_sentence = ""
                continue

            # Add to current sentence
            if current_sentence:
                current_sentence += " " + line
            else:
                current_sentence = line

            # Check if sentence ends (ends with punctuation)
            if re.search(r"[.!?;:]\s*$", current_sentence):
                joined.append(current_sentence)
                current_sentence = ""

        # Add remaining
        if current_sentence:
            joined.append(current_sentence)

        return " ".join(joined)

    def process_page_content(
        self,
        lines: list[str],
        page_number: int,
        confidence_scores: list[float] | None = None,
    ) -> list[ContentSegment]:
        """
        Process a page of text into structured segments
        Returns list of ContentSegment with proper classification
        """
        if not lines:
            return []

        segments = []
        confidence_scores = confidence_scores or [0.9] * len(lines)

        # Calculate average line length for header detection
        avg_line_length = sum(len(line) for line in lines) / max(len(lines), 1)

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Skip empty lines
            if not line:
                i += 1
                continue

            # Skip blacklisted content
            if self.header_detector.is_blacklisted(line):
                logger.debug(f"Skipping blacklisted line: {line}")
                i += 1
                continue

            # Skip footer/header
            if self.header_detector.is_footer_header(line):
                logger.debug(f"Skipping footer/header: {line}")
                i += 1
                continue

            # Detect header level
            content_type, confidence = self.header_detector.detect_header_level(
                line,
                i,
                len(lines),
                avg_line_length,
                font_size=None,
            )

            # Skip separator rows (confidence <= 0)
            if confidence <= 0:
                logger.debug(f"Skipping separator row: {line}")
                i += 1
                continue

            # Collect related lines for non-headers (but not TABLE_ROW)
            if content_type in [ContentType.BODY, ContentType.LIST]:
                collected_lines = [line]
                j = i + 1

                # Collect following lines until we hit a likely header or table row or end
                while j < len(lines):
                    next_line = lines[j].strip()

                    if not next_line:
                        j += 1
                        continue

                    if self.header_detector.is_blacklisted(next_line):
                        break

                    next_type, next_conf = self.header_detector.detect_header_level(
                        next_line, j, len(lines), avg_line_length
                    )

                    # Break on headers or table rows
                    if next_type in [
                        ContentType.H1,
                        ContentType.H2,
                        ContentType.H3,
                        ContentType.TABLE_ROW,
                    ]:
                        break

                    # Skip separator rows
                    if next_conf <= 0:
                        break

                    collected_lines.append(next_line)
                    j += 1

                # Join collected lines
                joined_text = self.join_sentences(collected_lines)

                if joined_text:
                    segment = ContentSegment(
                        content=self.clean_text(joined_text),
                        content_type=content_type,
                        page_number=page_number,
                        confidence=confidence,
                        original_lines=collected_lines,
                    )
                    segments.append(segment)

                i = j
            else:
                # Header or TABLE_ROW - create single segment
                segment = ContentSegment(
                    content=self.clean_text(line),
                    content_type=content_type,
                    page_number=page_number,
                    confidence=confidence,
                    original_lines=[line],
                )
                segments.append(segment)
                i += 1

        return segments


def process_extracted_text(
    text: str,
    page_number: int = 0,
    split_by_newline: bool = True,
) -> list[ContentSegment]:
    """
    Main entry point for text processing
    Converts raw OCR text into structured segments

    Args:
        text: Raw extracted text
        page_number: Page number for reference
        split_by_newline: Whether to split text by newlines first

    Returns:
        List of ContentSegment objects
    """
    lines = text.split("\n") if split_by_newline else [text]
    cleaner = TextCleaner()

    return cleaner.process_page_content(lines, page_number)
