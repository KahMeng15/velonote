"""
Document generator for creating styled PDF outputs from structured content.
Supports headers, embedded images, markdown formatting, and professional styling.
"""

import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Flowable,
    Frame,
    PageBreak,
    PageTemplate,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.platypus import Image as RLImage

from app.processing.image_extractor import ExtractedImage
from app.processing.text_processor import ContentSegment, ContentType

logger = logging.getLogger(__name__)


class HeaderFooter:
    """Handles headers and footers for PDF pages"""

    def __init__(self, note_title: str, page_size=letter):
        self.note_title = note_title
        self.page_size = page_size
        self.page_number = 0

    def draw_header_footer(self, canvas_obj, doc):
        """Draw header and footer on each page"""
        canvas_obj.saveState()

        page_width = self.page_size[0]
        page_height = self.page_size[1]

        # Header
        canvas_obj.setFont("Helvetica-Bold", 10)
        canvas_obj.drawString(0.5 * inch, page_height - 0.4 * inch, self.note_title)

        # Footer
        canvas_obj.setFont("Helvetica", 8)
        canvas_obj.drawRightString(page_width - 0.5 * inch, 0.3 * inch, f"Page {self.page_number}")

        canvas_obj.restoreState()


class StyleSheet:
    """Custom stylesheet for document"""

    @staticmethod
    def get_styles() -> dict[str, ParagraphStyle]:
        """Get custom styles for document — sizes/colors match template defaults"""
        styles = getSampleStyleSheet()

        custom_styles = {
            "H1": ParagraphStyle(
                name="H1_custom",
                parent=styles["Heading1"],
                fontSize=28,
                textColor=colors.HexColor("#1A1A2E"),
                spaceAfter=8,
                spaceBefore=8,
                fontName="Helvetica-Bold",
                leading=34,
            ),
            "H2": ParagraphStyle(
                name="H2_custom",
                parent=styles["Heading2"],
                fontSize=24,
                textColor=colors.HexColor("#2C3E50"),
                spaceAfter=8,
                spaceBefore=8,
                fontName="Helvetica-Bold",
                leading=29,
            ),
            "H3": ParagraphStyle(
                name="H3_custom",
                parent=styles["Heading3"],
                fontSize=20,
                textColor=colors.HexColor("#34495E"),
                spaceAfter=8,
                spaceBefore=8,
                fontName="Helvetica-Bold",
                leading=24,
            ),
            "H4": ParagraphStyle(
                name="H4_custom",
                parent=styles["Heading3"],
                fontSize=16,
                textColor=colors.HexColor("#333333"),
                spaceAfter=6,
                spaceBefore=6,
                fontName="Helvetica-Bold",
                leading=20,
            ),
            "H5": ParagraphStyle(
                name="H5_custom",
                parent=styles["Heading3"],
                fontSize=14,
                textColor=colors.HexColor("#555555"),
                spaceAfter=4,
                spaceBefore=4,
                fontName="Helvetica-Bold",
                leading=17,
            ),
            "Body": ParagraphStyle(
                name="Body_custom",
                parent=styles["BodyText"],
                fontSize=11,
                leading=13,
                alignment=TA_JUSTIFY,
                textColor=colors.HexColor("#2c3e50"),
                spaceAfter=8,
                spaceBefore=0,
            ),
            "List": ParagraphStyle(
                name="List_custom",
                parent=styles["BodyText"],
                fontSize=11,
                leading=13,
                leftIndent=20,
                textColor=colors.HexColor("#2c3e50"),
                spaceAfter=4,
            ),
            "OrderedList": ParagraphStyle(
                name="OrderedList_custom",
                parent=styles["BodyText"],
                fontSize=11,
                leading=13,
                leftIndent=20,
                textColor=colors.HexColor("#2c3e50"),
                spaceAfter=4,
            ),
            "TableRow": ParagraphStyle(
                name="TableRow_custom",
                parent=styles["BodyText"],
                fontSize=10,
                textColor=colors.HexColor("#2c3e50"),
                spaceAfter=4,
                fontName="Courier",
            ),
            "Caption": ParagraphStyle(
                name="Caption_custom",
                parent=styles["Normal"],
                fontSize=9,
                textColor=colors.HexColor("#7f8c8d"),
                alignment=TA_CENTER,
                spaceAfter=6,
            ),
            "Code": ParagraphStyle(
                name="Code_custom",
                parent=styles["BodyText"],
                fontSize=9,
                fontName="Courier",
                textColor=colors.HexColor("#2c3e50"),
                backColor=colors.HexColor("#ecf0f1"),
                leftIndent=15,
                spaceAfter=6,
                leading=11,
            ),
        }

        return custom_styles


class DocumentGenerator:
    """Generates styled PDF from structured content"""

    _fonts_registered = False

    def __init__(
        self,
        resource_id: str,
        note_title: str,
        page_size=letter,
    ):
        self.resource_id = resource_id
        self.note_title = note_title
        self._template_config = None
        from app.utils.storage import StorageManager
        self.output_dir = StorageManager.get_exports_dir_for_resource(resource_id)

        self.page_size = page_size
        self._template_config = None
        self._footer_show_page_number = True
        self._footer_custom_text = ""

        # Create output directory
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

        self.output_pdf = os.path.join(self.output_dir, "OUTPUT.pdf")
        self.styles = StyleSheet.get_styles()
        self._register_fonts()

    @classmethod
    def _register_fonts(cls):
        """Register custom TrueType fonts if not already registered"""
        if cls._fonts_registered:
            return

        try:
            fonts_dir = os.path.join(
                os.path.dirname(os.path.dirname(__file__)), "static", "fonts", "Instrument_Sans"
            )
            if os.path.exists(fonts_dir):
                pdfmetrics.registerFont(
                    TTFont("Instrument Sans", os.path.join(fonts_dir, "InstrumentSans-Regular.ttf"))
                )
                pdfmetrics.registerFont(
                    TTFont(
                        "Instrument Sans-Bold", os.path.join(fonts_dir, "InstrumentSans-Bold.ttf")
                    )
                )
                pdfmetrics.registerFont(
                    TTFont(
                        "Instrument Sans-Italic",
                        os.path.join(fonts_dir, "InstrumentSans-Italic.ttf"),
                    )
                )
                pdfmetrics.registerFont(
                    TTFont(
                        "Instrument Sans-BoldItalic",
                        os.path.join(fonts_dir, "InstrumentSans-BoldItalic.ttf"),
                    )
                )
                pdfmetrics.registerFontFamily(
                    "Instrument Sans",
                    normal="Instrument Sans",
                    bold="Instrument Sans-Bold",
                    italic="Instrument Sans-Italic",
                    boldItalic="Instrument Sans-BoldItalic",
                )
                logger.info("[PDF Export] Custom fonts loaded successfully.")
        except Exception as e:
            logger.warning(f"[PDF Export] Failed to register custom fonts: {e}")

        cls._fonts_registered = True

    def generate_pdf(
        self,
        content_segments: list[ContentSegment],
        extracted_images: list[ExtractedImage] | None = None,
        include_toc: bool = True,
        include_cover: bool = True,
        template_config: dict | None = None,
        progress_callback=None,
    ) -> str:
        """
        Generate styled PDF from content segments
        Returns path to generated PDF
        """
        try:
            extracted_images = extracted_images or []
            self._template_config = template_config or {}

            # Debug logging
            logger.info(f"[PDF Export] Template config type: {type(template_config)}")
            logger.info(f"[PDF Export] Template config value: {template_config}")

            if template_config and isinstance(template_config, str):
                # If it's a string, parse it as JSON
                import json

                try:
                    template_config = json.loads(template_config)
                    self._template_config = template_config
                    logger.info(f"[PDF Export] Parsed JSON template config: {template_config}")
                except:
                    logger.warning("[PDF Export] Failed to parse template config as JSON")

            if progress_callback:
                progress_callback("Preparing document", 10)

            # Apply template page configuration
            from reportlab.lib.pagesizes import A3, A4, legal, letter

            page_size = letter
            orientation = "portrait"

            if template_config and "page" in template_config:
                page_cfg = template_config["page"]
                logger.info(f"[PDF Export] Page config: {page_cfg}")

                # Page size
                size_name = page_cfg.get("size", "A4").upper()
                if size_name == "A4":
                    page_size = A4
                elif size_name == "LETTER":
                    page_size = letter
                elif size_name == "LEGAL":
                    page_size = legal
                elif size_name == "A3":
                    page_size = A3

                # Orientation - swap dimensions for landscape
                orientation = page_cfg.get("orientation", "portrait").lower()
                logger.info(f"[PDF Export] Orientation: {orientation}")
                if orientation == "landscape":
                    page_size = (page_size[1], page_size[0])  # Swap width/height

            self.page_size = page_size

            # Resolve footer settings for use in _on_page callback
            if template_config and "footer" in template_config:
                fc = template_config["footer"]
                self._footer_show_page_number = fc.get("show_page_number", True)
                self._footer_custom_text = fc.get("custom_text", "")
            else:
                self._footer_show_page_number = True
                self._footer_custom_text = ""

            # Get margins (in mm, convert to inches)
            margins_mm = {"top": 25, "bottom": 25, "left": 19, "right": 19}
            if template_config and "page" in template_config:
                page_cfg = template_config["page"]
                if "margins" in page_cfg:
                    margins_mm.update(page_cfg["margins"])

            # Convert mm to inches (1 inch = 25.4 mm)
            margins_in = {k: v / 25.4 for k, v in margins_mm.items()}

            # Get column count
            num_columns = 1
            if template_config and "page" in template_config:
                num_columns = template_config["page"].get("columns", 1)
                logger.info(f"[PDF Export] Columns: {num_columns}")

            # Create document with appropriate template
            if num_columns > 1:
                doc = self._create_multicolumn_document(
                    self.output_pdf, self.page_size, margins_in, num_columns
                )
                use_multicolumn = True
                logger.info(f"[PDF Export] Using multicolumn layout with {num_columns} columns")
            else:
                doc = SimpleDocTemplate(
                    self.output_pdf,
                    pagesize=self.page_size,
                    rightMargin=margins_in["right"] * inch,
                    leftMargin=margins_in["left"] * inch,
                    topMargin=margins_in["top"] * inch,
                    bottomMargin=margins_in["bottom"] * inch,
                )
                use_multicolumn = False
                logger.info("[PDF Export] Using single column layout")

            # Build story
            story = []

            # Add title page (not affected by columns)
            if include_cover:
                if progress_callback:
                    progress_callback("Creating cover page", 20)
                story.extend(self._create_title_page())
                story.append(PageBreak())

            # Add table of contents (not affected by columns)
            if include_toc:
                if progress_callback:
                    progress_callback("Building table of contents", 35)
                story.extend(self._create_table_of_contents(content_segments))
                story.append(PageBreak())

            # Add content
            if progress_callback:
                progress_callback("Rendering content", 50)
            story.extend(self._create_content(content_segments, extracted_images))

            # Build PDF
            if progress_callback:
                progress_callback("Building PDF", 80)

            # BaseDocTemplate doesn't support onFirstPage/onLaterPages callbacks
            if use_multicolumn:
                doc.build(story)
            else:
                doc.build(story, onFirstPage=self._on_page, onLaterPages=self._on_page)

            if progress_callback:
                progress_callback("Complete", 100)

            logger.info(f"Generated PDF: {self.output_pdf}")
            return self.output_pdf

        except Exception as e:
            logger.error(f"Error generating PDF: {e}")
            raise

    def _create_multicolumn_document(
        self, filename: str, page_size: tuple, margins_in: dict, num_columns: int
    ) -> BaseDocTemplate:
        """Create a BaseDocTemplate with multiple column frames"""
        doc = BaseDocTemplate(
            filename,
            pagesize=page_size,
            rightMargin=margins_in["right"] * inch,
            leftMargin=margins_in["left"] * inch,
            topMargin=margins_in["top"] * inch,
            bottomMargin=margins_in["bottom"] * inch,
        )

        # Calculate frame dimensions
        page_width = page_size[0]
        page_height = page_size[1]
        available_width = page_width - (margins_in["left"] + margins_in["right"]) * inch
        available_height = page_height - (margins_in["top"] + margins_in["bottom"]) * inch

        # Column gap
        column_gap = 0.3 * inch
        column_width = (available_width - (num_columns - 1) * column_gap) / num_columns

        # Create frames for each column
        frames = []
        for col in range(num_columns):
            x = margins_in["left"] * inch + col * (column_width + column_gap)
            frame = Frame(
                x,
                margins_in["bottom"] * inch,
                column_width,
                available_height,
                leftPadding=0,
                rightPadding=0,
                topPadding=0,
                bottomPadding=0,
            )
            frames.append(frame)

        # Create page template with multiple frames
        template = PageTemplate(id="default", frames=frames)
        doc.addPageTemplates([template])

        return doc

    def _create_title_page(self) -> list[Flowable]:
        """Create title page using cover_page config if available"""
        story = []

        # Read cover page config
        cover_cfg = {}
        if self._template_config and "cover_page" in self._template_config:
            cover_cfg = self._template_config["cover_page"]

        # Vertical alignment
        v_align = cover_cfg.get("v_align", "middle")
        if v_align == "top":
            story.append(Spacer(1, 0.5 * inch))
        elif v_align == "middle":
            story.append(Spacer(1, 3.5 * inch))
        else:  # bottom
            story.append(Spacer(1, 7.0 * inch))

        title_text = cover_cfg.get("h1_text") or self.note_title
        title_font_size = cover_cfg.get("title_size", 36)
        title_color = cover_cfg.get("title_color", "#1A1A2E")

        h2_text = cover_cfg.get("h2_text") or "Extracted and Processed Content"
        h2_size = cover_cfg.get("h2_size", 14)
        h2_color = cover_cfg.get("h2_color", "#7f8c8d")

        h_align_str = cover_cfg.get("h_align", "center")
        h_align = self._get_alignment(h_align_str)

        show_date = cover_cfg.get("show_date", True)

        # Title
        title_style = ParagraphStyle(
            "CoverTitle",
            fontSize=title_font_size,
            textColor=colors.HexColor(title_color),
            alignment=h_align,
            fontName="Instrument Sans-Bold",
            spaceAfter=12,
            leading=title_font_size * 1.2,
        )
        story.append(Paragraph(title_text, title_style))

        story.append(Spacer(1, 0.1 * inch))

        # Subtitle (H2)
        subtitle_style = ParagraphStyle(
            "CoverSubtitle",
            fontSize=h2_size,
            textColor=colors.HexColor(h2_color),
            alignment=h_align,
            fontName="Instrument Sans",
            spaceAfter=12,
            leading=h2_size * 1.2,
        )
        story.append(Paragraph(h2_text, subtitle_style))

        # Date (only if show_date is True)
        if show_date:
            story.append(Spacer(1, 0.2 * inch))
            meta_style = ParagraphStyle(
                "CoverMeta",
                fontSize=10,
                textColor=colors.HexColor("#95a5a6"),
                alignment=h_align,
                fontName="Instrument Sans",
                spaceAfter=6,
            )
            story.append(
                Paragraph(f"Generated: {datetime.now().strftime('%B %d, %Y')}", meta_style)
            )

        return story

    def _create_table_of_contents(self, content_segments: list[ContentSegment]) -> list[Flowable]:
        """Create table of contents"""
        story = []

        # TOC Title
        toc_title = ParagraphStyle(
            "TOC_Title",
            fontSize=16,
            textColor=colors.HexColor("#1a1a1a"),
            fontName="Helvetica-Bold",
            spaceAfter=12,
        )
        story.append(Paragraph("Table of Contents", toc_title))

        story.append(Spacer(1, 0.2 * inch))

        # TOC entries
        toc_entry_style = ParagraphStyle(
            "TOC_Entry",
            fontSize=11,
            leftIndent=20,
            spaceAfter=6,
            textColor=colors.HexColor("#2c3e50"),
        )

        for segment in content_segments:
            if segment.content_type in [ContentType.H1, ContentType.H2]:
                indent = 0 if segment.content_type == ContentType.H1 else 20
                entry_style = ParagraphStyle(
                    f"TOC_{segment.content_type.value}",
                    parent=toc_entry_style,
                    leftIndent=indent,
                )
                story.append(Paragraph(f"• {segment.content[:50]}...", entry_style))

        return story

    def _create_content(
        self,
        content_segments: list[ContentSegment],
        extracted_images: list[ExtractedImage],
    ) -> list[Flowable]:
        """Create main content"""
        story = []

        # Create image lookup by page
        images_by_page = {}
        for img in extracted_images:
            if img.page_number not in images_by_page:
                images_by_page[img.page_number] = []
            images_by_page[img.page_number].append(img)

        # Process segments, collecting consecutive table rows
        i = 0
        while i < len(content_segments):
            segment = content_segments[i]

            # Check if this is a table row - collect all consecutive table rows
            if segment.content_type == ContentType.TABLE_ROW:
                table_segments = []
                while (
                    i < len(content_segments)
                    and content_segments[i].content_type == ContentType.TABLE_ROW
                ):
                    table_segments.append(content_segments[i])
                    i += 1

                # Render the table
                table_flowable = self._render_table(table_segments)
                if table_flowable:
                    story.append(table_flowable)
                    # Add spacing after table only if not using template
                    if not self._template_config or "elements" not in self._template_config:
                        story.append(Spacer(1, 0.2 * inch))
                continue

            # Regular paragraph rendering with template styles
            style_name = self._get_style_name_for_segment(segment)
            style = self.styles.get(style_name, self.styles["Body"])

            # Apply template element style if available
            if self._template_config and "elements" in self._template_config:
                style = self._apply_template_style(style, style_name)

            story.append(Paragraph(self._prepare_content(segment, style_name), style))

            # Only add extra spacing if not using template (template spacing is in ParagraphStyle)
            if not self._template_config or "elements" not in self._template_config:
                story.append(Spacer(1, 0.08 * inch))

            # Add images for this page
            if segment.page_number in images_by_page:
                for img in images_by_page[segment.page_number]:
                    story.extend(self._add_image(img))

            i += 1

        return story

    def _get_style_name_for_segment(self, segment: ContentSegment) -> str:
        """Map content type to style name"""
        type_to_style = {
            ContentType.H1: "H1",
            ContentType.H2: "H2",
            ContentType.H3: "H3",
            ContentType.H4: "H4",
            ContentType.H5: "H5",
            ContentType.LIST: "List",
            ContentType.ORDERED_LIST: "OrderedList",
            ContentType.CODE: "Code",
            ContentType.BODY: "Body",
            ContentType.NOTE_TITLE: "NoteTitle",
            ContentType.SUBJECT_NAME: "SubjectName",
            ContentType.GROUP_NAME: "GroupName",
        }
        return type_to_style.get(segment.content_type, "Body")

    def _apply_template_style(self, base_style: ParagraphStyle, style_name: str) -> ParagraphStyle:
        """Apply template element styles to paragraph style"""
        elements_config = self._template_config.get("elements", {})
        spacing_config = self._template_config.get("spacing", {})
        code_config = self._template_config.get("code_block", {})

        # Map style names to element keys
        style_map = {
            "H1": "h1",
            "H2": "h2",
            "H3": "h3",
            "H4": "h4",
            "H5": "h5",
            "Body": "paragraph",
            "List": "list",
            "OrderedList": "list",
            "Code": "code",
            "NoteTitle": "note_title",
            "SubjectName": "subject_name",
            "GroupName": "group_name",
        }

        element_key = style_map.get(style_name)
        if not element_key:
            return base_style

        elem_config = elements_config.get(element_key, {})

        # Override for code blocks if code_block config exists
        if style_name == "Code" and code_config:
            elem_config = {
                "font_size": code_config.get("font_size", 9),
                "text_color": code_config.get("text_color", "#2c3e50"),
                "background_color": code_config.get("background_color", "#f8f9fa"),
                "margin_top": 8,
                "margin_bottom": 8,
            }

        # Get spacing settings
        line_spacing = spacing_config.get("line_spacing", 1.15)

        # Element-specific margins (fallback to global paragraph spacing if not set)
        margin_top = elem_config.get("margin_top", spacing_config.get("paragraph_spacing", 8))
        margin_bottom = elem_config.get("margin_bottom", spacing_config.get("paragraph_spacing", 8))

        # Calculate leading from line_spacing
        base_font_size = elem_config.get("font_size", base_style.fontSize)
        leading = base_font_size * line_spacing

        # Get alignment
        alignment = self._get_alignment(elem_config.get("alignment", "left"))

        # Get colors and font info
        text_color = elem_config.get("text_color", "#2C3E50")
        bg_color = elem_config.get("background_color")
        if bg_color and bg_color.lower() == "#ffffff":
            bg_color = None

        font_weight = elem_config.get("font_weight", "normal")

        # Create modified style with all template settings
        style = ParagraphStyle(
            name=f"{base_style.name}_templated",
            parent=base_style,
            fontSize=base_font_size,
            textColor=colors.HexColor(text_color),
            backColor=colors.HexColor(bg_color) if bg_color else None,
            fontName="Instrument Sans-Bold" if font_weight == "bold" else "Instrument Sans",
            alignment=alignment,
            leading=leading,
            spaceAfter=margin_bottom,
            spaceBefore=margin_top,
        )

        # Apply list-specific indentations
        if style_name in ["List", "OrderedList"]:
            list_left_margin = spacing_config.get("list_left_margin", 24)
            list_bullet_gap = spacing_config.get("list_bullet_gap", 6)
            # leftIndent is total indent, firstLineIndent is relative to leftIndent
            # to make bullet hang, firstLineIndent should be negative.
            style.leftIndent = list_left_margin + list_bullet_gap
            style.firstLineIndent = -(list_bullet_gap + 10)  # 10 is approximate bullet width

        return style

    def _parse_inline_markdown(self, text: str) -> str:
        """
        Convert inline markdown syntax to ReportLab paragraph XML.
        ReportLab Paragraph supports a subset of HTML-like tags:
          <b>, <i>, <u>, <strike>, <font color="...">.
        Order matters: process bold+italic first, then bold, then italic.
        """
        import html
        import re

        # Escape HTML special chars first so we don't double-escape our own tags
        text = html.escape(text, quote=False)

        # Bold + italic: ***text*** or ___text___
        text = re.sub(r"\*\*\*(.+?)\*\*\*", r"<b><i>\1</i></b>", text)
        text = re.sub(r"___(.+?)___", r"<b><i>\1</i></b>", text)

        # Bold: **text** or __text__
        text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
        text = re.sub(r"__(.+?)__", r"<b>\1</b>", text)

        # Italic: *text* or _text_ (not inside a word)
        text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"<i>\1</i>", text)
        text = re.sub(r"(?<!\w)_(.+?)_(?!\w)", r"<i>\1</i>", text)

        # Strikethrough: ~~text~~
        text = re.sub(r"~~(.+?)~~", r"<strike>\1</strike>", text)

        # Inline code: `code`
        text = re.sub(r"`([^`]+)`", r'<font face="Courier">\1</font>', text)

        return text

    def _prepare_content(self, segment: ContentSegment, style_name: str) -> str:
        """
        Prepare segment content for Paragraph:
        - Strip and replace list prefix chars with proper bullet / number
        - Apply inline markdown → ReportLab XML conversion
        """
        import re

        content = segment.content

        list_cfg = self._template_config.get("list_config", {})
        custom_bullet = list_cfg.get("custom_bullet", "•")
        num_format = list_cfg.get("number_format", "1.")

        if style_name == "List":
            # Strip leading markdown list markers (-, *, +, •) and replace with custom_bullet
            content = re.sub(r"^\s*[-*+•]\s+", "", content)
            content = f"{custom_bullet}\u00a0\u00a0{content}"
        elif style_name == "OrderedList":
            # Strip leading "1." / "2." etc. and replace with the configured format
            m = re.match(r"^\s*(\d+)\.\s+", content)
            if m:
                num = m.group(1)
                content = re.sub(r"^\s*\d+\.\s+", "", content)

                # Apply number format
                prefix = f"{num}."
                if num_format == "1)":
                    prefix = f"{num})"
                elif num_format == "1]":
                    prefix = f"{num}]"

                content = f"{prefix}\u00a0\u00a0{content}"

        return self._parse_inline_markdown(content)

    def _get_alignment(self, alignment_str: str):
        """Convert alignment string to reportlab enum"""
        alignment_map = {
            "left": TA_LEFT,
            "center": TA_CENTER,
            "right": TA_RIGHT,
            "justify": TA_JUSTIFY,
        }
        return alignment_map.get(alignment_str, TA_LEFT)

    def _render_table(self, table_segments: list[ContentSegment]) -> Flowable | None:
        """
        Render markdown table rows as a ReportLab Table, applying all table
        styles from template_config["table"] if available.
        """
        if not table_segments:
            return None

        # Parse markdown table format
        rows = []
        for segment in table_segments:
            cells = [cell.strip() for cell in segment.content.split("|")]
            cells = [c for c in cells if c and not c.startswith("---")]
            if cells:
                rows.append(cells)

        if not rows:
            return None

        # Read table config from template
        tbl_cfg = {}
        if self._template_config and "table" in self._template_config:
            tbl_cfg = self._template_config["table"]

        header_bg = tbl_cfg.get("header_bg_color", "#593f8f")
        header_fg = tbl_cfg.get("header_text_color", "#ffffff")
        odd_row_color = tbl_cfg.get("odd_row_color", "#ffffff")
        even_row_color = tbl_cfg.get("even_row_color", "#f5f4fb")
        border_color = tbl_cfg.get("border_color", "#cccccc")
        border_width = float(tbl_cfg.get("border_width", 0.5))
        repeat_header = tbl_cfg.get("repeat_header", True)
        cell_padding = int(tbl_cfg.get("cell_padding", 6))
        header_fs = int(tbl_cfg.get("header_font_size", 10))
        body_fs = int(tbl_cfg.get("body_font_size", 9))
        tbl_cfg.get("alignment", "center").upper()

        try:
            # Calculate available width for the table, accounting for:
            # 1. Page margins
            # 2. Number of layout columns (tables flow inside a single column frame)
            # 3. Column gap between frames
            margins_cfg = {}
            if self._template_config and "page" in self._template_config:
                margins_cfg = self._template_config["page"].get("margins", {})
            left_m = float(margins_cfg.get("left", 19)) / 25.4 * inch
            right_m = float(margins_cfg.get("right", 19)) / 25.4 * inch
            full_content_width = self.page_size[0] - left_m - right_m

            # Determine number of layout columns from template config
            layout_cols = 1
            if self._template_config and "page" in self._template_config:
                layout_cols = int(self._template_config["page"].get("columns", 1))

            # Each frame (column) is: (full_content_width - gaps) / num_columns
            column_gap = 0.3 * inch  # must match _create_multicolumn_document
            if layout_cols > 1:
                frame_width = (full_content_width - (layout_cols - 1) * column_gap) / layout_cols
            else:
                frame_width = full_content_width

            # Number of data columns in this specific table
            num_table_cols = len(rows[0]) if rows else 1
            col_width = frame_width / num_table_cols

            # Convert raw cell strings → Paragraph objects so text wraps inside cells.
            # In ReportLab, plain strings NEVER word-wrap; Paragraphs always do.
            rl_alignment = self._get_alignment(tbl_cfg.get("alignment", "center"))
            header_cell_style = ParagraphStyle(
                "TblHeader",
                fontName="Helvetica-Bold",
                fontSize=header_fs,
                textColor=colors.HexColor(header_fg),
                alignment=rl_alignment,
                leading=header_fs * 1.3,
            )
            body_cell_style = ParagraphStyle(
                "TblBody",
                fontName="Helvetica",
                fontSize=body_fs,
                textColor=colors.HexColor("#2C3E50"),
                alignment=rl_alignment,
                leading=body_fs * 1.3,
            )

            para_rows = []
            for r_idx, row in enumerate(rows):
                cell_style = header_cell_style if r_idx == 0 else body_cell_style
                para_rows.append([Paragraph(str(cell), cell_style) for cell in row])

            # Build alternating row background commands
            row_bg_cmds = []
            for r_idx in range(1, len(rows)):
                color_hex = odd_row_color if r_idx % 2 == 1 else even_row_color
                row_bg_cmds.append(
                    ("BACKGROUND", (0, r_idx), (-1, r_idx), colors.HexColor(color_hex))
                )

            table_style_cmds = [
                # Header row background (text styling is inside the Paragraph style)
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_bg)),
                # Vertical alignment
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                # Padding
                ("TOPPADDING", (0, 0), (-1, -1), cell_padding),
                ("BOTTOMPADDING", (0, 0), (-1, -1), cell_padding),
                ("LEFTPADDING", (0, 0), (-1, -1), cell_padding),
                ("RIGHTPADDING", (0, 0), (-1, -1), cell_padding),
                # Border
                ("GRID", (0, 0), (-1, -1), border_width, colors.HexColor(border_color)),
            ] + row_bg_cmds

            repeat_rows = 1 if repeat_header else 0
            table = Table(para_rows, colWidths=[col_width] * num_table_cols, repeatRows=repeat_rows)
            table.setStyle(TableStyle(table_style_cmds))
            return table
        except Exception as e:
            logger.warning(f"Failed to render table: {e}")
            return None

    def _add_image(self, image_obj: ExtractedImage) -> list[Flowable]:
        """Add image to story"""
        story = []

        try:
            if not os.path.exists(image_obj.file_path):
                logger.warning(f"Image file not found: {image_obj.file_path}")
                return story

            # Add caption if exists
            if image_obj.caption:
                caption_para = Paragraph(image_obj.caption, self.styles["Caption"])
                story.append(caption_para)

            # Add image
            img = RLImage(image_obj.file_path, width=5 * inch, height=3 * inch)
            story.append(img)

            # Add image metadata if it contains text
            if image_obj.text_content:
                meta_text = f"<i>Text in image: {image_obj.text_content[:100]}...</i>"
                story.append(Paragraph(meta_text, self.styles["Caption"]))

            story.append(Spacer(1, 0.2 * inch))

        except Exception as e:
            logger.error(f"Error adding image {image_obj.filename}: {e}")

        return story

    def _on_page(self, canvas_obj, doc):
        """Callback for page drawing — respects footer config from template"""
        canvas_obj.saveState()

        page_width = self.page_size[0]

        # Build footer text
        parts = ["Generated by velonote.vercel.app | Create notes and study smart!"]
        if self._footer_custom_text:
            parts.append(self._footer_custom_text)
        footer_text = " | ".join(parts)

        canvas_obj.setFont("Helvetica", 7)
        canvas_obj.drawString(0.5 * inch, 0.35 * inch, footer_text)

        # Page number on right (only if configured)
        if self._footer_show_page_number:
            canvas_obj.setFont("Helvetica", 8)
            canvas_obj.drawRightString(page_width - 0.5 * inch, 0.35 * inch, f"Page {doc.page}")

        canvas_obj.restoreState()

    def get_output_info(self) -> dict[str, Any]:
        """Get information about generated PDF"""
        try:
            if os.path.exists(self.output_pdf):
                file_size_mb = os.path.getsize(self.output_pdf) / (1024 * 1024)
                return {
                    "success": True,
                    "output_file": self.output_pdf,
                    "file_size_mb": round(file_size_mb, 2),
                    "generated_at": datetime.now().isoformat(),
                }
            else:
                return {
                    "success": False,
                    "error": "Output PDF not found",
                }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
            }
