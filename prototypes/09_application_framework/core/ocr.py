"""
LingoLens OCR Engine

Provides reusable functions for extracting text
from images using Tesseract OCR.

The engine supports both:

- Plain text extraction.
- Positional OCR with bounding boxes.

Positional OCR is used by the TranslationMap to
associate translated text with desktop coordinates.
"""

import logging

import pytesseract

from config import (
    TESSERACT_PATH,
    OCR_LANGUAGE_MAP,
    DEFAULT_OCR_LANGUAGES,
)


logger = logging.getLogger(__name__)


# ------------------------------------------------------------
# Configure Tesseract executable
# ------------------------------------------------------------

pytesseract.pytesseract.tesseract_cmd = (
    TESSERACT_PATH
)


# ------------------------------------------------------------
# OCR Language Configuration
# ------------------------------------------------------------

def _get_tesseract_languages(
    languages=None,
) -> str:
    """
    Convert LingoLens OCR language names into
    Tesseract language codes.

    Parameters
    ----------
    languages : list[str] | None
        LingoLens OCR language names.

    Returns
    -------
    str
        Tesseract language expression.
    """

    if languages is None:
        languages = DEFAULT_OCR_LANGUAGES

    return "+".join(
        OCR_LANGUAGE_MAP[language]
        for language in languages
    )


# ------------------------------------------------------------
# Plain Text OCR
# ------------------------------------------------------------

def extract_text(
    image,
    languages=None,
):
    """
    Extract text from a PIL Image.

    This function intentionally preserves the
    original LingoLens OCR API.

    Parameters
    ----------
    image : PIL.Image
        Image to process.

    languages : list[str] | None
        OCR language names.

    Returns
    -------
    str
        Extracted text.
    """

    tesseract_languages = (
        _get_tesseract_languages(
            languages
        )
    )

    return pytesseract.image_to_string(
        image,
        lang=tesseract_languages,
    )


# ------------------------------------------------------------
# OCR Diagnostics
# ------------------------------------------------------------

def _log_ocr_diagnostics(results):
    """
    Log a compact confidence summary for positional OCR.

    This function is diagnostic only.

    It does not modify, filter, reorder, or otherwise
    alter OCR results.
    """

    if not results:
        logger.info(
            "OCR diagnostics: no OCR results."
        )
        return

    confidences = [
        result["confidence"]
        for result in results
        if result["confidence"] >= 0
    ]

    if not confidences:
        logger.info(
            "OCR diagnostics: %d result(s), "
            "no valid confidence values.",
            len(results),
        )
        return

    average_confidence = (
        sum(confidences) / len(confidences)
    )

    below_50 = sum(
        confidence < 50
        for confidence in confidences
    )

    below_70 = sum(
        confidence < 70
        for confidence in confidences
    )

    below_80 = sum(
        confidence < 80
        for confidence in confidences
    )

    low_confidence_results = [
        result
        for result in results
        if 0 <= result["confidence"] < 50
    ]

    low_confidence_results.sort(
        key=lambda result: result["confidence"]
    )

    low_confidence_sample = [
        (
            result["text"],
            round(result["confidence"], 1),
        )
        for result in low_confidence_results[:10]
    ]

    logger.info(
        "OCR diagnostics: results=%d, "
        "confidence_avg=%.1f, "
        "confidence_min=%.1f, "
        "confidence_max=%.1f, "
        "below50=%d, "
        "below70=%d, "
        "below80=%d.",
        len(results),
        average_confidence,
        min(confidences),
        max(confidences),
        below_50,
        below_70,
        below_80,
    )

    if low_confidence_sample:
        logger.info(
            "OCR diagnostics: lowest-confidence "
            "results=%s",
            low_confidence_sample,
        )


# ------------------------------------------------------------
# Positional OCR
# ------------------------------------------------------------

def extract_text_data(
    image,
    languages=None,
    psm=3,
):
    """
    Extract text together with its position
    inside the supplied image.

    Tesseract provides word-level bounding boxes
    together with block, paragraph and line
    identifiers.

    Empty OCR results are ignored.

    Parameters
    ----------
    image : PIL.Image
        Image to process.

    languages : list[str] | None
        OCR language names.

    psm : int
        Tesseract Page Segmentation Mode.

        Default:
            3 - Fully automatic page segmentation,
                but no OSD.

        Live Mode may explicitly use:
            7 - Treat image as a single text line.

    Returns
    -------
    list[dict]
        OCR results.

        Each item contains:

            {
                "text": str,
                "left": int,
                "top": int,
                "width": int,
                "height": int,
                "confidence": float,
                "block_num": int,
                "par_num": int,
                "line_num": int,
            }

        Coordinates are relative to the supplied
        image.
    """

    tesseract_languages = (
        _get_tesseract_languages(
            languages
        )
    )

    # --------------------------------------------------------
    # Tesseract page segmentation and OCR engine
    #
    # OEM 1 explicitly selects Tesseract's LSTM OCR engine.
    # PSM remains configurable so existing callers keep their
    # current page-segmentation behavior.
    # --------------------------------------------------------

    positional_ocr_config = (
        f"--oem 1 --psm {psm}"
    )

    data = pytesseract.image_to_data(
        image,
        lang=tesseract_languages,
        config=positional_ocr_config,
        output_type=pytesseract.Output.DICT,
    )

    results = []

    count = len(
        data.get("text", [])
    )

    for index in range(count):

        text = (
            data["text"][index]
            .strip()
        )

        if not text:
            continue

        try:

            confidence = float(
                data["conf"][index]
            )

        except (
            ValueError,
            TypeError,
        ):

            confidence = -1.0

        results.append(
            {
                "text": text,

                "left": int(
                    data["left"][index]
                ),

                "top": int(
                    data["top"][index]
                ),

                "width": int(
                    data["width"][index]
                ),

                "height": int(
                    data["height"][index]
                ),

                "confidence": confidence,

                # --------------------------------------------
                # Tesseract hierarchy
                #
                # These identifiers allow the Controller
                # Image Pipeline to group words belonging
                # to the same text block and preserve
                # Tesseract's detected reading order.
                # --------------------------------------------

                "block_num": int(
                    data["block_num"][index]
                ),

                "par_num": int(
                    data["par_num"][index]
                ),

                "line_num": int(
                    data["line_num"][index]
                ),
            }
        )

    # --------------------------------------------------------
    # Diagnostic logging
    #
    # IMPORTANT:
    # The OCR results themselves are not changed.
    # --------------------------------------------------------

    _log_ocr_diagnostics(results)

    return results