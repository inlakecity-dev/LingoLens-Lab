"""
LingoLens Application Controller

Coordinates the workflow between the UI
and the application core.
"""

from config import (
    DEFAULT_SOURCE_LANGUAGE,
    DEFAULT_TARGET_LANGUAGE,
)

from core.capture import capture_region
from core.ocr import extract_text
from core.translator import translate_text
from core.history import save_translation


def translate_region(
    x1,
    y1,
    x2,
    y2,
    ocr_languages=None,
    source_language=DEFAULT_SOURCE_LANGUAGE,
    target_language=DEFAULT_TARGET_LANGUAGE,
):
    """
    Capture a screen region, extract text,
    translate it and save the translation history.

    Args:
        x1, y1:
            Top-left coordinates.

        x2, y2:
            Bottom-right coordinates.

        source_language (str):
            Source language.
            Default: Auto Detect

        target_language (str):
            Target language.
            Default: English

    Returns:
        dict:
            {
                "original": str,
                "translation": str,
                "history_file": pathlib.Path,
            }
    """

    # Capture selected screen region
    image = capture_region(
        x1,
        y1,
        x2,
        y2,
    )

    # Extract text from image
    original_text = extract_text(
        image,
        languages=ocr_languages,
    )

    # Translate extracted text
    translated_text = translate_text(
        original_text,
        source_language,
        target_language,
    )

    # Save translation history
    history_file = save_translation(
        original_text,
        translated_text,
        source_language,
        target_language,
    )

    # Return results
    return {
        "original": original_text,
        "translation": translated_text,
        "history_file": history_file,
        "ocr_language": ocr_languages,
        "source_language": source_language,
        "target_language": target_language,
    }