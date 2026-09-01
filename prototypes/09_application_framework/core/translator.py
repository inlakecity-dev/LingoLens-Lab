"""
core/translator.py

LingoLens Translation Engine

Provides reusable functions for translating text.
"""

from __future__ import annotations

import threading
import time

from deep_translator import GoogleTranslator

from config import (
    DEFAULT_SOURCE_LANGUAGE,
    DEFAULT_TARGET_LANGUAGE,
)

from logger import logger


MODULE = "TRANSLATOR"


# --------------------------------------------------
# Translation configuration
# --------------------------------------------------

#
# GoogleTranslator may wait indefinitely when the
# underlying network request does not return.
#
# Keep translation calls bounded so the Controller
# Live worker cannot remain blocked indefinitely.
#

TRANSLATION_TIMEOUT = 15.0


#
# GoogleTranslator requests are serialized.
#
# ControllerImagePipeline may translate multiple OCR
# blocks concurrently. GoogleTranslator should not be
# allowed to send multiple Google requests simultaneously
# from LingoLens.
#

_TRANSLATION_LOCK = threading.Lock()


#
# Retry a transient Google server response.
#

TRANSLATION_RETRIES = 2


#
# Small delay between retry attempts.
#

TRANSLATION_RETRY_DELAY = 1.0


# --------------------------------------------------
# Translation response validation
# --------------------------------------------------

def _is_invalid_translation_response(
    translated_text,
):
    """
    Return True when the translation service returned
    an obvious server/error response instead of an
    actual translation.

    Some external translation failures can be returned
    as text rather than raised as Python exceptions.

    Those responses must never enter the TranslationMap.
    """

    if translated_text is None:
        return True

    value = str(
        translated_text
    ).strip()

    if not value:
        return True

    normalized = value.lower()

    error_markers = (
        "error 500",
        "server error",
        "there was an error",
        "please try again later",
        "that's all we know",
        "that’s all we know",
    )

    return any(
        marker in normalized
        for marker in error_markers
    )


# --------------------------------------------------
# Single translation request
# --------------------------------------------------

def _perform_translation(
    text,
    source,
    target,
):
    """
    Perform one GoogleTranslator request.

    The caller must hold _TRANSLATION_LOCK.

    Returns
    -------
    tuple
        (
            translated_text,
            error,
        )
    """

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

    if worker.is_alive():

        return (
            None,
            TimeoutError(
                "Translation request timed out."
            ),
        )

    if result["error"] is not None:

        return (
            None,
            result["error"],
        )

    return (
        result["text"],
        None,
    )


# --------------------------------------------------
# Single Text Translation
# --------------------------------------------------

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
        cannot be completed, times out, or the
        translation service returns an obvious
        error response.
    """

    # --------------------------------------------------
    # Empty input
    # --------------------------------------------------

    if not text or not text.strip():
        return ""

    text = text.strip()

    # --------------------------------------------------
    # Same source and target language
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
    # Serialize GoogleTranslator requests.
    # --------------------------------------------------

    with _TRANSLATION_LOCK:

        for attempt in range(
            1,
            TRANSLATION_RETRIES + 1,
        ):

            logger.info(
                MODULE,
                "Translation request attempt "
                f"{attempt}/{TRANSLATION_RETRIES}."
            )

            translated_text, error = (
                _perform_translation(
                    text,
                    source,
                    target,
                )
            )

            # ------------------------------------------
            # Timeout
            # ------------------------------------------

            if isinstance(
                error,
                TimeoutError,
            ):

                logger.error(
                    MODULE,
                    "Translation timed out after "
                    f"{TRANSLATION_TIMEOUT:.1f} seconds "
                    f"({len(text)} characters)."
                )

                return ""

            # ------------------------------------------
            # Python exception
            # ------------------------------------------

            if error is not None:

                logger.error(
                    MODULE,
                    "Translation failed: "
                    f"{error}"
                )

                if attempt < TRANSLATION_RETRIES:

                    time.sleep(
                        TRANSLATION_RETRY_DELAY
                    )

                    continue

                return ""

            # ------------------------------------------
            # Validate Google response
            # ------------------------------------------

            if _is_invalid_translation_response(
                translated_text
            ):

                logger.warning(
                    MODULE,
                    "Translation service returned an "
                    "invalid/error response on attempt "
                    f"{attempt}."
                )

                if attempt < TRANSLATION_RETRIES:

                    time.sleep(
                        TRANSLATION_RETRY_DELAY
                    )

                    continue

                logger.error(
                    MODULE,
                    "Translation service returned an "
                    "invalid/error response. "
                    "The response will not be added to "
                    "the TranslationMap."
                )

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

    return ""


# --------------------------------------------------
# Batch Translation
# --------------------------------------------------

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
    """

    # --------------------------------------------------
    # Validate input
    # --------------------------------------------------

    if not texts:
        return []

    normalized_texts = []

    for text in texts:

        if text is None:

            normalized_texts.append("")

        else:

            normalized_texts.append(
                str(text).strip()
            )

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
    # Serialize batch request.
    # --------------------------------------------------

    with _TRANSLATION_LOCK:

        for attempt in range(
            1,
            TRANSLATION_RETRIES + 1,
        ):

            logger.info(
                MODULE,
                "Batch translation request attempt "
                f"{attempt}/{TRANSLATION_RETRIES}."
            )

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

                    translated_texts = (
                        translator.translate_batch(
                            normalized_texts
                        )
                    )

                    result["texts"] = (
                        translated_texts
                    )

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

            # ------------------------------------------
            # Timeout
            # ------------------------------------------

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

            # ------------------------------------------
            # Python exception
            # ------------------------------------------

            if result["error"] is not None:

                logger.warning(
                    MODULE,
                    "Batch translation failed on attempt "
                    f"{attempt}: "
                    f"{result['error']}"
                )

                if attempt < TRANSLATION_RETRIES:

                    time.sleep(
                        TRANSLATION_RETRY_DELAY
                    )

                    continue

                return [
                    ""
                    for _ in normalized_texts
                ]

            translated_texts = (
                result["texts"]
            )

            # ------------------------------------------
            # Validate result
            # ------------------------------------------

            if translated_texts is None:

                logger.warning(
                    MODULE,
                    "Batch translation returned no "
                    "result on attempt "
                    f"{attempt}."
                )

                if attempt < TRANSLATION_RETRIES:

                    time.sleep(
                        TRANSLATION_RETRY_DELAY
                    )

                    continue

                return [
                    ""
                    for _ in normalized_texts
                ]

            if not isinstance(
                translated_texts,
                (list, tuple),
            ):

                translated_texts = [
                    translated_texts
                ]

            translated_texts = [
                ""
                if _is_invalid_translation_response(
                    translated
                )
                else str(
                    translated
                ).strip()
                for translated in translated_texts
            ]

            # ------------------------------------------
            # Check whether every result is valid.
            # ------------------------------------------

            invalid_result = (
                any(
                    not translated
                    for translated
                    in translated_texts
                )
            )

            if invalid_result:

                logger.warning(
                    MODULE,
                    "Batch translation returned one or "
                    "more invalid translation results "
                    f"on attempt {attempt}."
                )

                if attempt < TRANSLATION_RETRIES:

                    time.sleep(
                        TRANSLATION_RETRY_DELAY
                    )

                    continue

            # ------------------------------------------
            # Preserve positional alignment.
            # ------------------------------------------

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

    return [
        ""
        for _ in normalized_texts
    ]