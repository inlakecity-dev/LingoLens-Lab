"""
LingoLens OCR Engine

Provides reusable functions for extracting text
from images using Tesseract OCR.
"""

import pytesseract

from config import (
    TESSERACT_PATH,
    OCR_LANGUAGE_MAP,
    DEFAULT_OCR_LANGUAGES,
)

# Configure Tesseract executable
pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH


def extract_text(image, languages=None):
    """
    Extract text from a PIL Image.

    Args:
        image (PIL.Image):
            Image to process.

        languages (list[str] | None):
            OCR language names.

    Returns:
        str:
            Extracted text.
    """

    if languages is None:
        languages = DEFAULT_OCR_LANGUAGES

    tesseract_languages = "+".join(
        OCR_LANGUAGE_MAP[language]
        for language in languages
    )

    return pytesseract.image_to_string(
        image,
        lang=tesseract_languages
    )