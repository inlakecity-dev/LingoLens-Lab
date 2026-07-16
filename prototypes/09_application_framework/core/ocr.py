"""
LingoLens OCR Engine

Provides reusable functions for extracting text
from images using Tesseract OCR.
"""

import pytesseract

from config import TESSERACT_PATH

# Configure Tesseract executable
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def extract_text(image, languages=None):
    """
    Extract text from a PIL Image.

    Args:
        image (PIL.Image):
            Image to process.

        languages (str, optional):
            Tesseract language codes separated by '+'.
            If None, Tesseract will use its default language.

    Returns:
        str:
            Extracted text.
    """

    if languages:
        return pytesseract.image_to_string(
            image,
            lang=languages
        )

    return pytesseract.image_to_string(image)