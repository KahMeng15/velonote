import logging
import os
import uuid
from dataclasses import dataclass

import cv2
import numpy as np
import pytesseract
from pdf2image import convert_from_path
from PIL import Image

logger = logging.getLogger(__name__)


@dataclass
class ExtractedImage:
    """Represents an extracted image from a document page."""

    filename: str
    page_number: int
    position_x: float = 0.0
    position_y: float = 0.0
    width: float = 0.0
    height: float = 0.0
    caption: str = ""
    text_content: str = ""
    confidence: float = 0.8
    is_diagram: bool = False
    file_path: str = ""

    def to_dict(self):
        import dataclasses

        return dataclasses.asdict(self)


class ImageExtractor:
    """
    Uses OpenCV to extract significant non-text graphical elements (Figures).
    """

    def __init__(self, output_dir="output/images", resource_id: str = "0"):
        self.resource_id = resource_id
        # Convert to string and handle default empty ID
        if resource_id and resource_id != "0":
            self.output_dir = os.path.join(output_dir, resource_id)
        else:
            self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)

    def process_page_image(self, pil_image: Image.Image, page_num: int) -> list:
        """
        Process page image, detect figures, save them, return HTML img tags.
        """
        try:
            # Convert PIL to CV2
            img = np.array(pil_image)
            # RGB to BGR
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

            # 1. Edge Detection / Gradient
            # Morphological gradient to outlines
            grad = cv2.morphologyEx(
                gray, cv2.MORPH_GRADIENT, cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
            )

            # 2. Binarize
            _, binary = cv2.threshold(grad, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

            # 3. Connect components to form blocks
            # Aggressive merging to group scattered background elements
            kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (50, 20))
            connected = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

            # 4. Find Contours
            contours, _ = cv2.findContours(connected, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            found_images = []

            height, width = img.shape[:2]

            for cnt in contours:
                x, y, w, h = cv2.boundingRect(cnt)

                # Filter: Must be large enough to be a figure
                if w < 150 or h < 150:
                    continue

                # Filter: If it covers entire page, likely frame/border?
                if w > width * 0.9 and h > height * 0.9:
                    continue

                # Filter: Sidebars / Backgrounds touching edges
                # If an image touches X=0 or Right Edge, AND is tall/wide, it's likely decoration
                touches_side = (x < 10) or (x + w > width - 10)
                if touches_side and (h > height * 0.5):
                    continue

                # Filter: Aspect ratio (not too skinny) of 1:10
                if w / h > 12 or h / w > 12:
                    continue

                # Crop
                roi = img[y : y + h, x : x + w]

                # Filter: Flat Color Blocks (Low Variance)
                # Calculate Std Dev of grayscale
                roi_gray = gray[y : y + h, x : x + w]
                std_dev = np.std(roi_gray)
                # Flat block ~ 0. Textures > 20. Photos > 40.
                if std_dev < 20:
                    continue

                # Filter: Stylized Text (e.g. "M", "C", "TNtw")

                # Filter: Stylized Text (e.g. "M", "C", "TNtw")
                # Run quick OCR on the crop
                try:
                    text_content = pytesseract.image_to_string(roi, config="--psm 6").strip()
                    # If it recognizes a very short string (1-3 chars/digits), it's likely just a big letter.
                    # Real diagrams usually have no text (empty) or lots of text/labels.
                    if 0 < len(text_content) < 4:
                        continue

                    # Also "TNtw" might be 4 chars.
                    # Just aggressive filter: if contains ONLY alpha characters and length < 6?
                    if text_content.isalpha() and len(text_content) < 6:
                        continue

                except Exception:
                    pass  # If OCR fails, assume it's an image and keep it

                # Save
                filename = f"figure_p{page_num}_{uuid.uuid4().hex[:6]}.jpg"
                save_path = os.path.join(self.output_dir, filename)
                cv2.imwrite(save_path, roi)

                # HTML src should be relative to the HTML file (which is in 'output/')
                # So we use "images/filename"
                html_src = f"images/{filename}"

                found_images.append(
                    {
                        "path": save_path,
                        "y": y,  # Top position for sorting
                        "html": f'<img src="{html_src}" alt="Figure from Page {page_num}" style="max-width:100%;">',
                    }
                )

            return found_images

        except Exception as e:
            logger.error(f"Error extracting images: {e}")
            return []

    def extract_images_from_pdf(self, pdf_path: str) -> list:
        """
        Extract images from all pages of a PDF.
        """
        try:
            images = convert_from_path(pdf_path)
            all_found_images = []

            for i, image in enumerate(images):
                page_images = self.process_page_image(image, page_num=i + 1)
                all_found_images.extend(page_images)

            # Convert to ExtractedImage objects
            result = []
            for img_dict in all_found_images:
                # img_dict has keys: path, y, html
                # We need to map this to ExtractedImage
                import os

                filename = os.path.basename(img_dict["path"])

                # Try to parse page number from filename or use 0
                page_num = 0
                if "figure_p" in filename:
                    try:
                        page_num = int(filename.split("figure_p")[1].split("_")[0])
                    except:
                        pass

                extracted_img = ExtractedImage(
                    filename=filename,
                    page_number=page_num,
                    file_path=img_dict["path"],
                    position_y=img_dict.get("y", 0),
                    caption="Extracted Figure",
                )
                result.append(extracted_img)

            return result
        except Exception as e:
            logger.error(f"Error extracting images from PDF: {e}")
            return []
