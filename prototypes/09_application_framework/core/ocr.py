"""
LingoLens OCR Engine

Provides reusable functions for extracting text
from images using Tesseract OCR.
"""

import pytesseract

from config import TESSERACT_PATH, OCR_LANGUAGES

# Configure Tesseract executable
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def extract_text(image, languages=OCR_LANGUAGES):
    """
    Extract text from a PIL Image.

    Args:
        image (PIL.Image):
            Image to process.

        languages (str):
            Tesseract language codes separated by '+'.

    Returns:
        str:
            Extracted text.
    """

    return pytesseract.image_to_string(
        image,
        lang=languages
    )