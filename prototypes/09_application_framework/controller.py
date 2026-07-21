"""
LingoLens Application Controller

Coordinates the workflow between the UI
and the application core.
"""

import time

from core.capture import capture_region
from core.ocr import extract_text
from core.translator import translate_text
from core.history import save_translation
from config import (
    DEFAULT_SOURCE_LANGUAGE,
    DEFAULT_TARGET_LANGUAGE,
    OCR_LANGUAGES,
)


def translate_region(
    x1,
    y1,
    x2,
    y2,
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
                "status": str,
                "original": str,
                "translation": str,
                "history_file": pathlib.Path | None,
                "ocr_language": str,
                "source_language": str,
                "target_language": str,
            }
    """

    total_start = time.perf_counter()

    # --------------------------------------------------
    # Capture selected screen region
    # --------------------------------------------------

    start = time.perf_counter()

    image = capture_region(
        x1,
        y1,
        x2,
        y2,
    )

    print(f"Capture     : {time.perf_counter() - start:.3f} sec")

    # --------------------------------------------------
    # Extract text from image
    # --------------------------------------------------

    start = time.perf_counter()

    original_text = extract_text(image)

    print(f"OCR         : {time.perf_counter() - start:.3f} sec")

    # Stop if no text was detected

    if not original_text.strip():

        print(f"TOTAL       : {time.perf_counter() - total_start:.3f} sec\n")

        return {
            "status": "no_text",
            "original": "",
            "translation": "",
            "history_file": None,
            "ocr_language": OCR_LANGUAGES,
            "source_language": source_language,
            "target_language": target_language,
        }

    # --------------------------------------------------
    # Translate extracted text
    # --------------------------------------------------

    start = time.perf_counter()

    translated_text = translate_text(
        original_text,
        source_language,
        target_language,
    )

    print(f"Translation : {time.perf_counter() - start:.3f} sec")

    # --------------------------------------------------
    # Save translation history
    # --------------------------------------------------

    start = time.perf_counter()

    history_file = save_translation(
        original_text,
        translated_text,
        source_language,
        target_language,
    )

    print(f"History     : {time.perf_counter() - start:.3f} sec")

    print("-" * 35)
    print(f"TOTAL       : {time.perf_counter() - total_start:.3f} sec\n")

    # --------------------------------------------------
    # Return results
    # --------------------------------------------------

    return {
        "status": "success",
        "original": original_text,
        "translation": translated_text,
        "history_file": history_file,
        "ocr_language": OCR_LANGUAGES,
        "source_language": source_language,
        "target_language": target_language,
    }