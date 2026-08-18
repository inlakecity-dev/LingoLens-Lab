"""
core/translator.py

LingoLens Translation Engine

Provides reusable functions for translating text.
"""

from __future__ import annotations

import threading

from deep_translator import GoogleTranslator

from config import (
    DEFAULT_SOURCE_LANGUAGE,
    DEFAULT_TARGET_LANGUAGE,
)

from logger import logger


MODULE = "TRANSLATOR"


# --------------------------------------------------
# Translation timeout
# --------------------------------------------------

#
# GoogleTranslator may wait indefinitely when the
# underlying network request does not return.
#
# Keep translation calls bounded so the Controller
# Live worker cannot remain blocked indefinitely.
#

TRANSLATION_TIMEOUT = 15.0


def translate_text(
    text,
    source=DEFAULT_SOURCE_LANGUAGE,
    target=DEFAULT_TARGET_LANGUAGE,
):
    """
    Translate text into another language.

    Args
    ----
    text : str
        Text to translate.

    source : str
        Source language code.
        Default: Auto Detect.

    target : str
        Target language code.
        Default: English.

    Returns
    -------
    str
        Translated text.

        Returns the original text when source and
        target languages are the same.

        Returns an empty string when translation
        cannot be completed or times out.
    """

    # --------------------------------------------------
    # Empty input
    # --------------------------------------------------

    if not text or not text.strip():
        return ""

    text = text.strip()

    # --------------------------------------------------
    # Same source and target language
    #
    # No external translation service is required.
    # --------------------------------------------------

    if (
        source
        and target
        and source.lower() == target.lower()
    ):
        return text

    logger.info(
        MODULE,
        "Translation started "
        f"({len(text)} characters)."
    )

    # --------------------------------------------------
    # Translation worker
    #
    # GoogleTranslator does not expose a reliable
    # timeout through the current application API.
    #
    # Run the external request separately so the
    # caller has a bounded wait.
    # --------------------------------------------------

    result = {
        "text": None,
        "error": None,
    }

    def translation_worker():
        try:

            translator = GoogleTranslator(
                source=source,
                target=target,
            )

            translated_text = translator.translate(
                text
            )

            result["text"] = translated_text

        except Exception as error:

            result["error"] = error

    worker = threading.Thread(
        target=translation_worker,
        name="TranslationWorker",
        daemon=True,
    )

    worker.start()

    worker.join(
        TRANSLATION_TIMEOUT
    )

    # --------------------------------------------------
    # Translation timeout
    # --------------------------------------------------

    if worker.is_alive():

        logger.error(
            MODULE,
            "Translation timed out after "
            f"{TRANSLATION_TIMEOUT:.1f} seconds "
            f"({len(text)} characters)."
        )

        return ""

    # --------------------------------------------------
    # Translation failure
    # --------------------------------------------------

    if result["error"] is not None:

        logger.error(
            MODULE,
            "Translation failed: "
            f"{result['error']}"
        )

        #
        # Translation failure must never terminate
        # Live Mode or the DesktopObserver thread.
        #

        return ""

    # --------------------------------------------------
    # Validate result
    # --------------------------------------------------

    translated_text = result["text"]

    if translated_text is None:
        return ""

    translated_text = str(
        translated_text
    ).strip()

    logger.info(
        MODULE,
        "Translation completed "
        f"({len(text)} characters)."
    )

    return translated_text


def translate_text_batch(
    texts,
    source=DEFAULT_SOURCE_LANGUAGE,
    target=DEFAULT_TARGET_LANGUAGE,
):
    """
    Translate multiple text blocks in one translation
    request.

    This function is intended primarily for Live Mode,
    where positional OCR may produce multiple text blocks
    from the same changed region.

    Parameters
    ----------
    texts : list[str]
        Text blocks to translate.

    source : str
        Source language code.
        Default: Auto Detect.

    target : str
        Target language code.
        Default: English.

    Returns
    -------
    list[str]
        Translations in the same order as the supplied
        text blocks.

        Empty input returns an empty list.

        If a translation request fails or times out,
        an empty string is returned for each supplied
        text block.

    Notes
    -----
    The function intentionally preserves the order of
    the supplied text blocks so positional OCR results
    can be mapped back to their original desktop regions.
    """

    # --------------------------------------------------
    # Validate input
    # --------------------------------------------------

    if not texts:
        return []

    #
    # Normalize the input while preserving the original
    # list order.
    #

    normalized_texts = []

    for text in texts:

        if text is None:
            normalized_texts.append("")

        else:
            normalized_texts.append(
                str(text).strip()
            )

    #
    # Nothing to translate.
    #

    if not any(
        text
        for text in normalized_texts
    ):
        return [
            ""
            for _ in normalized_texts
        ]

    # --------------------------------------------------
    # Same source and target language
    #
    # No external translation service is required.
    #
    # Preserve each text exactly as the translated
    # result for that block.
    # --------------------------------------------------

    if (
        source
        and target
        and source.lower() == target.lower()
    ):

        logger.info(
            MODULE,
            "Batch translation skipped because "
            "source and target languages are identical "
            f"({len(normalized_texts)} text block(s))."
        )

        return [
            text
            for text in normalized_texts
        ]

    logger.info(
        MODULE,
        "Batch translation started for "
        f"{len(normalized_texts)} text block(s)."
    )

    # --------------------------------------------------
    # Translation worker
    #
    # A single GoogleTranslator instance is created for
    # the entire batch.
    #
    # This avoids creating a separate translator object
    # for every OCR text block.
    # --------------------------------------------------

    result = {
        "texts": None,
        "error": None,
    }

    def translation_worker():
        try:

            translator = GoogleTranslator(
                source=source,
                target=target,
            )

            translated_texts = translator.translate_batch(
                normalized_texts
            )

            result["texts"] = translated_texts

        except Exception as error:

            result["error"] = error

    worker = threading.Thread(
        target=translation_worker,
        name="TranslationBatchWorker",
        daemon=True,
    )

    worker.start()

    worker.join(
        TRANSLATION_TIMEOUT
    )

    # --------------------------------------------------
    # Translation timeout
    # --------------------------------------------------

    if worker.is_alive():

        logger.error(
            MODULE,
            "Batch translation timed out after "
            f"{TRANSLATION_TIMEOUT:.1f} seconds "
            f"({len(normalized_texts)} text block(s))."
        )

        return [
            ""
            for _ in normalized_texts
        ]

    # --------------------------------------------------
    # Translation failure
    # --------------------------------------------------

    if result["error"] is not None:

        logger.error(
            MODULE,
            "Batch translation failed: "
            f"{result['error']}"
        )

        #
        # Preserve positional alignment with the OCR
        # blocks even when the external service fails.
        #

        return [
            ""
            for _ in normalized_texts
        ]

    # --------------------------------------------------
    # Validate result
    # --------------------------------------------------

    translated_texts = result["texts"]

    if translated_texts is None:

        logger.error(
            MODULE,
            "Batch translation returned no result."
        )

        return [
            ""
            for _ in normalized_texts
        ]

    #
    # Ensure the result is a list so the public API has
    # predictable behaviour.
    #

    if not isinstance(
        translated_texts,
        (list, tuple),
    ):

        translated_texts = [
            translated_texts
        ]

    translated_texts = [
        ""
        if translated is None
        else str(translated).strip()
        for translated in translated_texts
    ]

    # --------------------------------------------------
    # Preserve positional alignment
    #
    # The Controller Pipeline expects one translation
    # result for every supplied text block.
    #
    # If the external service unexpectedly returns a
    # different number of results, pad or trim the list
    # rather than allowing an index mismatch downstream.
    # --------------------------------------------------

    if len(translated_texts) < len(
        normalized_texts
    ):

        translated_texts.extend(
            [
                ""
                for _ in range(
                    len(normalized_texts)
                    - len(translated_texts)
                )
            ]
        )

    elif len(translated_texts) > len(
        normalized_texts
    ):

        translated_texts = (
            translated_texts[
                :len(normalized_texts)
            ]
        )

    logger.info(
        MODULE,
        "Batch translation completed for "
        f"{len(normalized_texts)} text block(s)."
    )

    return translated_texts