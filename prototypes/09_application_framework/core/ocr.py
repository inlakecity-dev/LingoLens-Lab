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

import pytesseract

from config import (
    TESSERACT_PATH,
    OCR_LANGUAGE_MAP,
    DEFAULT_OCR_LANGUAGES,
)

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
# Positional OCR Result
# ------------------------------------------------------------

def extract_text_data(
    image,
    languages=None,
):
    """
    Extract text together with its position
    inside the supplied image.

    Tesseract provides word-level bounding boxes
    together with block and paragraph identifiers.

    Empty OCR results are ignored.

    Parameters
    ----------
    image : PIL.Image
        Image to process.

    languages : list[str] | None
        OCR language names.

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
            }

        Coordinates are relative to the supplied
        image.
    """

    tesseract_languages = (
        _get_tesseract_languages(
            languages
        )
    )

    data = pytesseract.image_to_data(
        image,
        lang=tesseract_languages,
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

                # ----------------------------------------
                # Tesseract hierarchy
                #
                # These identifiers allow the Controller
                # Image Pipeline to group words belonging
                # to the same text block.
                # ----------------------------------------

                "block_num": int(
                    data["block_num"][index]
                ),

                "par_num": int(
                    data["par_num"][index]
                ),
            }
        )

    return results