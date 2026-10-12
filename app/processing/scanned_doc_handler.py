"""
Scanned document detection and OCR pipeline.

Detects whether a PDF is scanned (no selectable text) and routes it through
the appropriate OCR pipeline. Supports printed text (Tesseract), handwriting
(Tesseract LSTM mode), and mixed documents.
"""

import logging
import re

logger = logging.getLogger(__name__)


class ScannedDocHandler:
    """Handles scanned documents: detection, OCR, and confidence analysis."""

    SCANNED_CHARS_PER_PAGE_THRESHOLD = 50
    HANDWRITING_CONF_THRESHOLD = 0.4
    PRINTED_CONF_THRESHOLD = 0.7

    def __init__(self):
        self._preprocessor = None

    @property
    def preprocessor(self):
        if self._preprocessor is None:
            try:
                from app.processing.image_preprocessor import ImagePreprocessor

                self._preprocessor = ImagePreprocessor()
            except ImportError:
                return None
        return self._preprocessor

    def is_scanned_pdf(self, pdf_path: str) -> tuple[bool, float]:
        try:
            import pdfplumber

            total_chars = 0
            page_count = 0
            with pdfplumber.open(pdf_path) as pdf:
                for page in pdf.pages:
                    text = page.extract_text() or ""
                    total_chars += len(text.strip())
                    page_count += 1

            if page_count == 0:
                return True, 1.0

            chars_per_page = total_chars / page_count
            if chars_per_page < 20:
                return True, 0.95
            elif chars_per_page < self.SCANNED_CHARS_PER_PAGE_THRESHOLD:
                return True, 0.75
            elif chars_per_page < 200:
                return True, 0.30
            return False, 0.05

        except ImportError:
            logger.warning("pdfplumber not available, assuming digital PDF")
            return False, 0.0
        except Exception as e:
            logger.warning(f"Error checking if PDF is scanned: {e}")
            return False, 0.0

    def detect_document_type(self, page_images: list) -> str:
        if not page_images:
            return "unknown"
        import numpy as np
        import pytesseract

        all_confidences = []
        for pil_img in page_images[:3]:
            try:
                import cv2

                gray = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2GRAY)
                data = pytesseract.image_to_data(gray, output_type=pytesseract.Output.DICT)
                confs = []
                for i, c in enumerate(data["conf"]):
                    if c != "-1" and data["text"][i].strip():
                        confs.append(float(c))
                all_confidences.extend(confs)
            except Exception as e:
                logger.warning(f"Error parsing confidence: {e}")
                continue

        if not all_confidences:
            return "diagram"

        avg_conf = float(np.mean(all_confidences)) / 100.0
        low_conf_ratio = sum(1 for c in all_confidences if float(c) < 40) / max(
            len(all_confidences), 1
        )
        high_conf_ratio = sum(1 for c in all_confidences if float(c) > 70) / max(
            len(all_confidences), 1
        )

        if high_conf_ratio > 0.8 and avg_conf > self.PRINTED_CONF_THRESHOLD:
            return "printed"
        elif low_conf_ratio > 0.8 and avg_conf < self.HANDWRITING_CONF_THRESHOLD:
            return "handwritten"
        elif low_conf_ratio > 0.3 and high_conf_ratio > 0.3:
            return "mixed"
        elif len(all_confidences) < 10:
            return "diagram"
        else:
            return "mixed"

    def ocr_pipeline(
        self, page_images: list, doc_type: str, lang: str = "eng", progress_callback=None
    ) -> str:
        import numpy as np
        import pytesseract

        all_pages_text = []
        total = len(page_images)

        for page_idx, pil_img in enumerate(page_images):
            if progress_callback:
                progress_callback(int((page_idx / total) * 80))

            import cv2

            cv_img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(cv_img, cv2.COLOR_BGR2GRAY)
            if self.preprocessor:
                if doc_type == "handwritten":
                    gray = self.preprocessor.enhance_contrast(gray)
                    gray = self.preprocessor.denoise(gray)
                    angle = self.preprocessor.deskew_angle(gray)
                    if abs(angle) > 0.5:
                        gray = self.preprocessor.rotate(gray, angle)
                elif doc_type == "printed":
                    gray = self.preprocessor.preprocess_scan(pil_img)
                elif doc_type == "mixed":
                    gray = self.preprocessor.preprocess_scan(pil_img)

            if doc_type == "handwritten":
                config = "--psm 6 --oem 1"
            elif doc_type == "mixed":
                config = "--psm 3 --oem 1"
            else:
                config = "--psm 3 --oem 3"

            try:
                page_text = pytesseract.image_to_string(gray, lang=lang, config=config)
            except Exception as e:
                logger.warning(f"OCR failed for page {page_idx + 1}: {e}")
                page_text = ""

            structured_lines = self._structure_ocr_text(page_text)
            all_pages_text.append(f"[Page {page_idx + 1}]\n{structured_lines}")

        if progress_callback:
            progress_callback(85)

        merged = "\n\n".join(all_pages_text)
        merged = self._merge_split_words(merged)
        merged = self._clean_ocr_artifacts(merged)

        return merged

    def _structure_ocr_text(self, text: str) -> str:
        lines = text.split("\n")
        structured = []
        for line in lines:
            stripped = line.strip()
            if not stripped:
                structured.append("")
                continue

            if re.match(r"^[A-Z][A-Z\s\-]{3,}$", stripped) and len(stripped) < 80:
                structured.append(f"## {stripped.title()}")
                continue

            upper_ratio = sum(1 for c in stripped if c.isupper()) / max(len(stripped), 1)
            if upper_ratio > 0.7 and len(stripped) > 10 and len(stripped) < 80:
                structured.append(f"### {stripped}")
                continue

            if stripped.startswith("•") or stripped.startswith("-") or stripped.startswith("*"):
                structured.append(f"- {stripped[1:].strip()}")
                continue

            if re.match(r"^\d+[.)]\s", stripped):
                structured.append(stripped)
                continue

            structured.append(stripped)

        return "\n".join(structured)

    def _merge_split_words(self, text: str) -> str:
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
        return text

    def _clean_ocr_artifacts(self, text: str) -> str:
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            # 1. Drop graph axes: lines with 3 or more isolated numbers separated by spaces
            if re.match(r"^([\d.]+\s+){3,}[\d.]+$", stripped):
                continue
            # 2. Drop pure symbol noise (e.g., ">}", "+", "-", "|", "<")
            if stripped and not any(c.isalnum() for c in stripped) and len(stripped) <= 4:
                continue
            cleaned_lines.append(line)

        text = "\n".join(cleaned_lines)
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[|¦]{2,}", "|", text)
        text = re.sub(r"[_]{4,}", "", text)
        text = re.sub(r"[•·]", "-", text)
        return text.strip()

    def process_scanned_pdf(self, pdf_path: str, progress_callback=None) -> str:
        try:
            from pdf2image import convert_from_path
        except ImportError:
            return "Error: pdf2image not installed. Cannot process scanned PDFs."

        if progress_callback:
            progress_callback(5, "Converting PDF to images...")

        try:
            page_images = convert_from_path(pdf_path)
        except Exception as e:
            return f"Error converting PDF to images: {e}"

        if not page_images:
            return "Error: No pages found in PDF."

        if progress_callback:
            progress_callback(15, "Detecting document type...")

        doc_type = self.detect_document_type(page_images)
        logger.info(f"Detected document type: {doc_type}")

        if progress_callback:
            progress_callback(20, f"Running OCR ({doc_type})...")

        markdown = self.ocr_pipeline(page_images, doc_type, progress_callback=progress_callback)

        if progress_callback:
            progress_callback(100, "OCR complete")

        return markdown

    def process_image_file(self, image_path: str, progress_callback=None) -> str:
        try:
            from PIL import Image
        except ImportError:
            return "Error: PIL not installed."

        pil_img = Image.open(image_path)
        doc_type = self.detect_document_type([pil_img])
        markdown = self.ocr_pipeline([pil_img], doc_type, progress_callback=progress_callback)
        return markdown
