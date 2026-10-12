"""
Image preprocessing pipeline for scanned documents.

Prepares camera-captured and scanned document images for OCR by correcting
perspective, deskewing, enhancing contrast, denoising, and binarizing.
Each step is optional and can be configured independently.
"""

import logging

logger = logging.getLogger(__name__)


class ImagePreprocessor:
    """Image preprocessing for scanned/handwritten document OCR."""

    def __init__(
        self,
        clahe_clip_limit: float = 2.0,
        clahe_grid_size: tuple = (8, 8),
        denoise_strength: float = 10.0,
        binarize_method: str = "sauvola",
    ):
        self.clahe_clip_limit = clahe_clip_limit
        self.clahe_grid_size = clahe_grid_size
        self.denoise_strength = denoise_strength
        self.binarize_method = binarize_method

    def preprocess_scan(self, pil_image) -> object:
        import cv2
        import numpy as np

        img = np.array(pil_image)
        if len(img.shape) == 3:
            gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
        else:
            gray = img

        gray = self.denoise(gray)
        gray = self.enhance_contrast(gray)
        angle = self.deskew_angle(gray)
        if abs(angle) > 0.5:
            gray = self.rotate(gray, angle)

        return gray

    def preprocess_scan_rgb(self, pil_image):
        import cv2
        import numpy as np

        img = np.array(pil_image)
        if len(img.shape) == 2:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGB)
        elif img.shape[2] == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2RGB)

        denoised = self.denoise_color(img)
        lab = cv2.cvtColor(denoised, cv2.COLOR_RGB2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=self.clahe_clip_limit, tileGridSize=self.clahe_grid_size)
        l = clahe.apply(l)
        enhanced = cv2.merge([l, a, b])
        enhanced = cv2.cvtColor(enhanced, cv2.COLOR_LAB2RGB)

        gray = cv2.cvtColor(enhanced, cv2.COLOR_RGB2GRAY)
        angle = self.deskew_angle(gray)
        if abs(angle) > 0.5:
            enhanced = self.rotate_color(enhanced, angle)

        return enhanced

    def deskew_angle(self, gray_img, max_angle: float = 15.0) -> float:
        import cv2
        import numpy as np

        binary = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
        coords = np.column_stack(np.where(binary > 0))
        if len(coords) < 10:
            return 0.0

        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) > max_angle:
            return 0.0
        return angle

    def rotate(self, gray_img, angle: float):
        import cv2

        h, w = gray_img.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            gray_img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        return rotated

    def rotate_color(self, rgb_img, angle: float):
        import cv2

        h, w = rgb_img.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            rgb_img, matrix, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE
        )
        return rotated

    def enhance_contrast(self, gray_img):
        import cv2

        clahe = cv2.createCLAHE(clipLimit=self.clahe_clip_limit, tileGridSize=self.clahe_grid_size)
        return clahe.apply(gray_img)

    def denoise(self, gray_img):
        import cv2

        return cv2.fastNlMeansDenoising(gray_img, h=self.denoise_strength)

    def denoise_color(self, rgb_img):
        import cv2

        return cv2.fastNlMeansDenoisingColored(
            rgb_img, h=self.denoise_strength, hColor=self.denoise_strength
        )

    def binarize(self, gray_img, method: str | None = None):
        import cv2

        method = method or self.binarize_method

        if method == "otsu":
            _, binary = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
            return binary

        elif method == "adaptive":
            return cv2.adaptiveThreshold(
                gray_img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 31, 2
            )

        elif method == "sauvola":
            try:
                import cv2
                from cv2 import ximgproc

                sauvola = ximgproc.createThreshSauvolaBlockSize(31)
                return sauvola.adaptiveThreshold(
                    gray_img, 255, cv2.ADAPTIVE_THRESH_MEAN_C, cv2.THRESH_BINARY, 31, 2
                )
            except (ImportError, AttributeError):
                return self.binarize(gray_img, "adaptive")

        _, binary = cv2.threshold(gray_img, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)
        return binary

    def detect_page_corners(self, gray_img):
        import cv2

        blurred = cv2.GaussianBlur(gray_img, (5, 5), 0)
        edged = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edged, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        contours = sorted(contours, key=cv2.contourArea, reverse=True)

        for contour in contours:
            peri = cv2.arcLength(contour, True)
            approx = cv2.approxPolyDP(contour, 0.02 * peri, True)
            if len(approx) == 4:
                return approx.reshape(4, 2).tolist()
        return None

    def correct_perspective(self, gray_img, corners=None):
        import cv2
        import numpy as np

        if corners is None:
            corners = self.detect_page_corners(gray_img)
        if corners is None:
            return gray_img

        corners = np.array(corners, dtype=np.float32)
        rect = np.zeros((4, 2), dtype=np.float32)
        s = corners.sum(axis=1)
        rect[0] = corners[np.argmin(s)]
        rect[2] = corners[np.argmax(s)]
        diff = np.diff(corners, axis=1)
        rect[1] = corners[np.argmin(diff)]
        rect[3] = corners[np.argmax(diff)]

        (tl, tr, br, bl) = rect
        width_a = np.linalg.norm(br - bl)
        width_b = np.linalg.norm(tr - tl)
        max_width = max(int(width_a), int(width_b))
        height_a = np.linalg.norm(tr - br)
        height_b = np.linalg.norm(tl - bl)
        max_height = max(int(height_a), int(height_b))

        dst = np.array(
            [[0, 0], [max_width - 1, 0], [max_width - 1, max_height - 1], [0, max_height - 1]],
            dtype=np.float32,
        )

        M = cv2.getPerspectiveTransform(rect, dst)
        return cv2.warpAffine(gray_img, M, (max_width, max_height))

    def estimate_ocr_confidence(self, gray_img):
        import numpy as np
        import pytesseract

        try:
            data = pytesseract.image_to_data(gray_img, output_type=pytesseract.Output.DICT)
            confs = [c for c in data["conf"] if c != "-1"]
            if confs:
                confs = [float(c) for c in confs if c != "-1"]
                return float(np.mean(confs)) / 100.0 if confs else 0.0
        except Exception:
            pass
        return 0.0
