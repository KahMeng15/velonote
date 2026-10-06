"""
Slide Normalizer & Markdown Cleaner.

Cleans and consolidates Markdown extracted from lecture slides (PDF/PPTX)
without requiring any cloud or local LLM.
"""

import re
import logging

logger = logging.getLogger(__name__)

# Common slide footers, copyright notices, and publisher branding
_FOOTER_PATTERNS = [
    re.compile(r"^\s*©\s*\d{4}.*", re.IGNORECASE),
    re.compile(r"^>\s*©\s*\d{4}.*", re.IGNORECASE),
    re.compile(r".*All Rights Reserved.*", re.IGNORECASE),
    re.compile(r".*May not be copied, scanned, or duplicated.*", re.IGNORECASE),
    re.compile(r".*password-protected website for classroom.*", re.IGNORECASE),
    re.compile(r"^\s*¢\s*[»\>]\s*CENGAGE.*", re.IGNORECASE),
    re.compile(r"^\s*[’‘*®©]?\s*Learning[\’\‘']?\s*$", re.IGNORECASE),
    re.compile(r"^\s*ky a Learning\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d+\s*$"),  # Standalone slide/page numbers (e.g., "12", "13")
    re.compile(r"^\s*\d+\s+©.*", re.IGNORECASE),
    re.compile(r"^FIGURE\s+\d+-\d+\s+.*\(cont’d\.\)$", re.IGNORECASE),
]

_HEADING_CONTINUATION_REGEX = re.compile(
    r"^(#{1,4}\s+)(.*?)(?:\s*[\(\[]\s*(?:\d+\s+of\s+\d+|part\s+\d+|cont\.?(?:inued)?)\s*[\)\]])\s*$",
    re.IGNORECASE,
)


def clean_slide_markdown(md: str) -> str:
    """
    Clean raw markdown extracted from slides:
    - Strips copyright notices, page numbers, and publisher branding
    - Consolidates continuation slides (e.g. 'Objectives (1 of 3)' -> 'Objectives')
    - Cleans OCR picture annotations
    - Normalizes empty bullets and excessive blank lines
    """
    if not md:
        return ""

    lines = md.splitlines()
    cleaned = []

    in_picture_text = False
    picture_buffer = []

    for line in lines:
        stripped = line.strip()

        # Handle picture text tags from pymupdf4llm / OCR
        if "<!-- Start of picture text -->" in line:
            in_picture_text = True
            picture_buffer = []
            continue
        if "<!-- End of picture text -->" in line:
            in_picture_text = False
            joined_pic = "\n".join(picture_buffer).strip()
            if joined_pic:
                # Discard if it is OCR gibberish, very short without keywords, or copyright
                is_junk = False
                if len(joined_pic) < 15 and not any(
                    kw in joined_pic for kw in ["cout", "cin", "int", "=", ";", "{", "}"]
                ):
                    is_junk = True
                if any(p.match(joined_pic) for p in _FOOTER_PATTERNS):
                    is_junk = True
                if not is_junk:
                    cleaned.append(joined_pic)
            picture_buffer = []
            continue

        if in_picture_text:
            sub_lines = line.replace("<br>", "\n").splitlines()
            for sl in sub_lines:
                sl_s = sl.strip()
                if not any(p.match(sl_s) for p in _FOOTER_PATTERNS):
                    picture_buffer.append(sl)
            continue

        # Drop standalone '-' or '—' or empty bullets
        if stripped in ["-", "—", "–", "*", "•"]:
            continue

        # Filter out boilerplate / footer lines
        if any(p.match(stripped) for p in _FOOTER_PATTERNS):
            continue

        cleaned.append(line)

    text = "\n".join(cleaned)

    # Consolidate continuation slide headers (e.g. "Objectives (1 of 3)" and "(2 of 3)")
    new_lines = []
    last_heading = None

    for line in text.splitlines():
        match = _HEADING_CONTINUATION_REGEX.match(line)
        if match:
            prefix = match.group(1)
            title = match.group(2).strip()
            current_heading = f"{prefix}{title}"
            if current_heading == last_heading:
                # Merge into the existing section without repeating the heading
                continue
            else:
                last_heading = current_heading
                new_lines.append(current_heading)
        else:
            if line.startswith("#"):
                last_heading = line.strip()
            new_lines.append(line)

    # Strip leading blank lines so the document title is at the beginning
    while new_lines and not new_lines[0].strip():
        new_lines.pop(0)

    lines = new_lines

    # 1. Merge cover slide Chapter/Topic heading with its subtitle into a single H1
    i = 0
    while i < min(len(lines), 10):
        m = re.match(
            r"^#{1,3}\s+(Chapter\s+\d+|Topic\s+\d+)\s*$", lines[i].strip(), re.IGNORECASE
        )
        if m:
            chapter_prefix = m.group(1).title()
            j = i + 1
            while j < min(len(lines), 10) and not lines[j].strip():
                j += 1
            if j < len(lines) and lines[j].strip() and not lines[j].strip().startswith(("#", "-", "*", ">")):
                subtitle = lines[j].strip()
                lines[i] = f"# {chapter_prefix}: {subtitle}"
                lines.pop(j)
                # Drop secondary textbook title noise if immediately following
                while j < len(lines) and not lines[j].strip():
                    j += 1
                if j < len(lines) and any(
                    kw in lines[j].lower()
                    for kw in ["edition", "programming:", "problem analysis to program"]
                ):
                    lines.pop(j)
            break
        i += 1

    # 2. Promote slide headings: if slide headers were extracted as ### without ##, promote them to ##
    other_headings = [l for l in lines[1:] if l.startswith("#")]
    has_other_h2 = any(re.match(r"^##\s+", l) for l in other_headings)
    if not has_other_h2 and lines:
        lines = [lines[0]] + [
            "## " + l[4:].strip() if re.match(r"^###\s+", l) else l for l in lines[1:]
        ]

    # 3. Demote only subsequent H1s in the middle of the document to ## (preserving the first H1)
    first_h1_found = False
    for idx in range(len(lines)):
        if lines[idx].startswith("# "):
            if not first_h1_found:
                first_h1_found = True
            else:
                lines[idx] = "#" + lines[idx]

    # 4. Normalize table captions and sub-elements (##### -> ###) to prevent hierarchy jumps
    norm_lines = []
    for l in lines:
        if re.match(r"^#{4,6}\s+", l):
            norm_lines.append("### " + re.sub(r"^#{4,6}\s+", "", l).strip())
        else:
            norm_lines.append(l)

    # 5. Strip residual HTML tags (like <u>) left over by PDF layout extractors
    norm_lines = [re.sub(r"</?u>", "", l) for l in norm_lines]

    text = "\n".join(norm_lines)

    # Collapse 3+ consecutive blank lines down to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"
