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
    OCR_LANGUAGE_MAP,
    SOURCE_LANGUAGE_MAP,
    TARGET_LANGUAGE_MAP,
)


class Controller:
    """
    Coordinates the workflow between the UI
    and the application core.
    """

    def __init__(self, app_settings):

        self.app_settings = app_settings

    def translate_region(
        self,
        x1,
        y1,
        x2,
        y2,
    ):
        """
        Capture a screen region, extract text,
        translate it and save the translation history.
        """

        # ----------------------------------------------
        # Read current settings
        # ----------------------------------------------

        source_language = SOURCE_LANGUAGE_MAP[
            self.app_settings.source_language
        ]

        target_language = TARGET_LANGUAGE_MAP[
            self.app_settings.target_language
        ]

        ocr_languages = "+".join(
            OCR_LANGUAGE_MAP[language]
            for language in self.app_settings.enabled_ocr_languages
        )

        total_start = time.perf_counter()

        # ----------------------------------------------
        # Capture selected screen region
        # ----------------------------------------------

        start = time.perf_counter()

        image = capture_region(
            x1,
            y1,
            x2,
            y2,
        )

        print(
            f"Capture     : {time.perf_counter() - start:.3f} sec"
        )

        # ----------------------------------------------
        # OCR
        # ----------------------------------------------

        start = time.perf_counter()

        original_text = extract_text(
            image,
            self.app_settings.enabled_ocr_languages
        )

        print(
            f"OCR         : {time.perf_counter() - start:.3f} sec"
        )

        if not original_text.strip():

            print(
                f"TOTAL       : {time.perf_counter() - total_start:.3f} sec\n"
            )

            return {
                "status": "no_text",
                "original": "",
                "translation": "",
                "history_file": None,
                "ocr_language": ocr_languages,
                "source_language": source_language,
                "target_language": target_language,
            }

        # ----------------------------------------------
        # Translation
        # ----------------------------------------------

        start = time.perf_counter()

        translated_text = translate_text(
            original_text,
            source_language,
            target_language,
        )

        print(
            f"Translation : {time.perf_counter() - start:.3f} sec"
        )

        # ----------------------------------------------
        # Save History
        # ----------------------------------------------

        start = time.perf_counter()

        history_file = save_translation(
            original_text,
            translated_text,
            source_language,
            target_language,
        )

        print(
            f"History     : {time.perf_counter() - start:.3f} sec"
        )

        print("-" * 35)
        print(
            f"TOTAL       : {time.perf_counter() - total_start:.3f} sec\n"
        )

        return {
            "status": "success",
            "original": original_text,
            "translation": translated_text,
            "history_file": history_file,
            "ocr_language": ocr_languages,
            "source_language": source_language,
            "target_language": target_language,
        }