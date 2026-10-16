import struct
import re
import logging

logger = logging.getLogger(__name__)


class PPTExtractor:
    """
    A pure Python extractor for legacy MS PowerPoint (.ppt) files.
    Parses OLE document binaries directly to extract slide contents from SlideContainers (1006)
    while avoiding slide master artifacts and broken heading heuristics.
    """

    # Common master slide placeholder texts to ignore
    IGNORED_TEXTS = {
        "click to edit master title style",
        "click to edit master text styles",
        "second level",
        "third level",
        "fourth level",
        "fifth level",
        "click to edit master subtitle style",
        "click to add title",
        "click to add subtitle",
        "click to add text",
        "title text",
        "subtitle text",
        "title area for autorayouts",
        "object area for autorayouts",
        "subtitle area for autorayouts",
        "<date/time>",
        "<footer>",
        "<header>",
        "<#>",
        "*",
    }

    # Mapping for Microsoft Symbol / Wingdings PUA and legacy encodings to Unicode
    SYMBOL_MAP = {
        "\uf0ce": "∈",
        "\uf0de": "⇒",
        "\uf0a8": "•",
        "\uf0b4": "×",
        "\uf0b8": "÷",
        "\uf0b1": "±",
        "\uf0b9": "≠",
        "\uf0a3": "≤",
        "\uf0b3": "≥",
        "\x0b": "\n",
        "\r\n": "\n",
        "\r": "\n",
        "ð": "•",
        "": "⇒",
        "": "∈",
    }

    @classmethod
    def _clean_text(cls, text: str) -> str:
        """Normalize common PPT symbol characters, carriage returns, and tabs."""
        for k, v in cls.SYMBOL_MAP.items():
            text = text.replace(k, v)
        text = re.sub(r"[ \t]+", " ", text)
        return text.strip()

    @classmethod
    def _is_heading(cls, line: str, is_doc_start: bool = False) -> int:
        """
        Determine if a line is a genuine heading.
        Returns:
            1: Main document title (H1)
            2: Section / Slide title (H2)
            0: Not a heading (body text, list item, equation, table cell, etc.)
        """
        t = line.strip()
        if not t:
            return 0

        # Disallow pure numbers, binary, hex, or short alphanumeric values (e.g. 10, 11, 100, 000, 1101)
        if re.match(r"^[0-9A-Fa-f\s,=+*/_()\-]+$", t) and not re.search(r"[A-Za-z]{3,}", t):
            return 0

        # Disallow lines containing math equations or comparisons
        if re.search(r"[=+*<>⇒∈≤≥÷±≠]", t):
            return 0

        # Explicit Chapter/Topic/Section markers
        if re.match(r"^(Chapter|Topic|Section)\s+\d+", t, re.IGNORECASE):
            return 1 if is_doc_start else 2

        # Multi-part numbered section (e.g., 2.1, 2.1), 2.2.3, 2.3.4) followed by letters
        if re.match(r"^\d+(\.\d+)+(\)|\.)?\s+[A-Za-z]", t):
            return 2

        # Labels like "Example:", "Note:", "Solution:", "Exercise:" are not headings
        if t.lower().startswith(("example", "note", "solution", "exercise")) or t.endswith(":"):
            return 0

        # Avoid table headers / common single nouns
        if t.lower() in {
            "decimal", "binary", "octal", "hexadecimal", "hundreds", "tens", "ones",
            "sign", "magnitude", "integer", "fraction", "topics"
        }:
            return 0

        # Standalone short titles: must contain 2 to 8 real words, capitalized, no terminal punctuation
        words = re.findall(r"[A-Za-z]+", t)
        if 2 <= len(words) <= 8 and len(t) < 70 and not t.endswith((".", ",", ";", ":", "?", "!")):
            if t.isupper() or t.istitle():
                return 1 if is_doc_start else 2

        return 0

    @classmethod
    def extract_text(cls, filepath: str) -> str:
        """
        Extracts text from a .ppt file and returns clean Markdown.
        Uses SlideContainer (recType=1006) boundaries to isolate slides and discard
        orphaned master slide artifacts.
        """
        try:
            with open(filepath, "rb") as f:
                data = f.read()
        except Exception as e:
            return f"Error reading PPT file: {e}"

        # Find all Slide containers (rec_type == 1006, ver == 0x0F)
        slides = []
        idx = 0
        data_len = len(data)
        while idx + 8 <= data_len:
            ver_inst, rec_type, rec_len = struct.unpack_from("<HHI", data, idx)
            ver = ver_inst & 0x0F
            if ver == 0x0F and rec_type == 1006 and idx + 8 + rec_len <= data_len:
                slides.append((idx, idx + 8 + rec_len))
            idx += 2

        # If slide containers were identified, extract per-slide
        if slides:
            return cls._extract_from_slides(data, slides)

        # Fallback for non-standard/uncontainerized PPT files
        return cls._extract_fallback(data)

    @classmethod
    def _extract_from_slides(cls, data: bytes, slides: list[tuple[int, int]]) -> str:
        slide_markdowns = []
        is_doc_start = True

        for s_num, (s_start, s_end) in enumerate(slides, 1):
            slide_data = data[s_start:s_end]
            items = []

            for marker, enc in [(b"\xA8\x0F", "latin-1"), (b"\xA0\x0F", "utf-16le")]:
                i = 0
                while True:
                    i = slide_data.find(marker, i)
                    if i == -1:
                        break
                    if i >= 2 and i + 6 <= len(slide_data):
                        rlen = struct.unpack_from("<I", slide_data, i + 2)[0]
                        if 0 < rlen < 100000 and i + 6 + rlen <= len(slide_data):
                            raw = slide_data[i + 6 : i + 6 + rlen].decode(enc, errors="replace")
                            cleaned = cls._clean_text(raw)
                            if (
                                cleaned
                                and cleaned != "*"
                                and cleaned.lower() not in cls.IGNORED_TEXTS
                            ):
                                items.append((i, cleaned))
                    i += 2

            items.sort(key=lambda x: x[0])

            # Deduplicate sequential identical strings within the slide
            unique_slide_items = []
            seen_slide = set()
            for _, t in items:
                if t not in seen_slide:
                    seen_slide.add(t)
                    unique_slide_items.append(t)

            if not unique_slide_items:
                continue

            slide_lines = []
            first_item = True
            for item in unique_slide_items:
                if first_item and is_doc_start:
                    title_lines = [l.strip() for l in item.split("\n") if l.strip()]
                    title_text = " - ".join(title_lines)
                    slide_lines.append(f"# {title_text}")
                    is_doc_start = False
                    first_item = False
                    continue
                first_item = False

                for line in item.split("\n"):
                    line = line.strip()
                    if not line or line == "*" or line.lower() in cls.IGNORED_TEXTS:
                        continue

                    h_level = cls._is_heading(line, is_doc_start=is_doc_start)
                    if h_level > 0:
                        slide_lines.append(f"{'#' * h_level} {line}")
                        is_doc_start = False
                    elif (
                        line.lower().startswith(("example", "note", "solution", "exercise"))
                        or line.endswith(":")
                    ):
                        slide_lines.append(f"**{line.rstrip(':')}:**")
                    elif re.match(r"^([0-9]+\.?[0-9]*[\)\.]|[-•*])\s*", line):
                        # Clean list bullet or numbered list
                        line = re.sub(r"^[•*]\s*", "- ", line)
                        slide_lines.append(line)
                    else:
                        slide_lines.append(f"- {line}")

            if slide_lines:
                slide_markdowns.append("\n\n".join(slide_lines))

        return "\n\n---\n\n".join(slide_markdowns)

    @classmethod
    def _extract_fallback(cls, data: bytes) -> str:
        """Global atom scan for files where SlideContainer boundaries could not be parsed."""
        strings = []
        for marker, enc in [(b"\xA8\x0F", "latin-1"), (b"\xA0\x0F", "utf-16le")]:
            idx = 0
            while True:
                idx = data.find(marker, idx)
                if idx == -1:
                    break
                if idx >= 2 and idx + 6 <= len(data):
                    rec_len = struct.unpack_from("<I", data, idx + 2)[0]
                    if 0 < rec_len < 100000 and idx + 6 + rec_len <= len(data):
                        text_data = data[idx + 6 : idx + 6 + rec_len]
                        try:
                            text = text_data.decode(enc, errors="replace")
                            clean_text = cls._clean_text(text)
                            if (
                                clean_text
                                and clean_text != "*"
                                and clean_text.lower() not in cls.IGNORED_TEXTS
                            ):
                                strings.append((idx, clean_text))
                        except Exception:
                            pass
                idx += 2

        strings.sort(key=lambda x: x[0])
        seen = set()
        markdown_lines = []
        is_doc_start = True

        for _, text in strings:
            if text in seen:
                continue
            seen.add(text)

            for line in text.split("\n"):
                line = line.strip()
                if not line or line == "*" or line.lower() in cls.IGNORED_TEXTS:
                    continue
                h_level = cls._is_heading(line, is_doc_start=is_doc_start)
                if h_level > 0:
                    markdown_lines.append(f"{'#' * h_level} {line}")
                    is_doc_start = False
                elif re.match(r"^([0-9]+\.?[0-9]*[\)\.]|[-•*])\s*", line):
                    line = re.sub(r"^[•*]\s*", "- ", line)
                    markdown_lines.append(line)
                elif (
                    line.lower().startswith(("example", "note", "solution", "exercise"))
                    or line.endswith(":")
                ):
                    markdown_lines.append(f"**{line.rstrip(':')}:**")
                else:
                    markdown_lines.append(f"- {line}")

        return "\n\n".join(markdown_lines)
