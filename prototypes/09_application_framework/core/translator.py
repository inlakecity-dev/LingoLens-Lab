"""
LingoLens Translation Engine

Provides reusable functions for translating text.
"""

from deep_translator import GoogleTranslator

from config import (
    DEFAULT_SOURCE_LANGUAGE,
    DEFAULT_TARGET_LANGUAGE,
)


def translate_text(
    text,
    source=DEFAULT_SOURCE_LANGUAGE,
    target=DEFAULT_TARGET_LANGUAGE,
):
    """
    Translate text into another language.

    Args:
        text (str):
            Text to translate.

        source (str):
            Source language code.
            Default: Auto Detect

        target (str):
            Target language code.
            Default: English

    Returns:
        str:
            Translated text.
    """

    if not text.strip():
        return ""

    return GoogleTranslator(
        source=source,
        target=target,
    ).translate(text)