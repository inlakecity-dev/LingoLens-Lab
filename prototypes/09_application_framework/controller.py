"""
LingoLens Application Controller

Coordinates the workflow between the UI
and the application core.
"""

import time
from tkinter import messagebox

from core.capture_engine import capture_region
from core.ocr import extract_text
from core.translator import translate_text
from core.history import save_translation
from core.translation_map import TranslationMap
from core.desktop_observer import DesktopObserver

from logger import logger

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

        # ----------------------------------------------
        # Core Components
        # ----------------------------------------------

        # Central application Translation Map
        self.translation_map = TranslationMap()

        # Live Desktop Observer
        self.desktop_observer = DesktopObserver(self)

    # --------------------------------------------------
    # IMAGE PROCESSING PIPELINE
    # --------------------------------------------------

    def process_image(self, image):
        """
        Process an image through the OCR,
        translation and history pipeline.

        This method is shared by the standard
        application workflow and the Floating
        Lens workflow.
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
        # OCR
        # ----------------------------------------------

        start = time.perf_counter()

        original_text = extract_text(
            image,
            self.app_settings.enabled_ocr_languages
        )

        ocr_time = time.perf_counter() - start

        print(
            f"OCR         : {ocr_time:.3f} sec"
        )

        if not original_text.strip():

            total_time = time.perf_counter() - total_start

            print(
                f"TOTAL       : {total_time:.3f} sec\n"
            )

            return {
                "status": "no_text",
                "original": "",
                "translation": "",
                "history_file": None,
                "ocr_language": ocr_languages,
                "source_language": source_language,
                "target_language": target_language,
                "ocr_time": ocr_time,
                "translation_time": 0,
                "history_time": 0,
                "total_time": total_time,
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

        translation_time = time.perf_counter() - start

        print(
            f"Translation : {translation_time:.3f} sec"
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

        history_time = time.perf_counter() - start

        print(
            f"History     : {history_time:.3f} sec"
        )

        total_time = time.perf_counter() - total_start

        print("-" * 35)

        print(
            f"TOTAL       : {total_time:.3f} sec\n"
        )

        return {
            "status": "success",
            "original": original_text,
            "translation": translated_text,
            "history_file": history_file,
            "ocr_language": ocr_languages,
            "source_language": source_language,
            "target_language": target_language,
            "ocr_time": ocr_time,
            "translation_time": translation_time,
            "history_time": history_time,
            "total_time": total_time,
        }

    def translate_region(
        self,
        x1,
        y1,
        x2,
        y2,
    ):
        """
        Capture a screen region and process it
        through the shared image processing
        pipeline.
        """

        # ----------------------------------------------
        # Capture selected screen region
        # ----------------------------------------------

        start = time.perf_counter()

        region = capture_region(
            x1,
            y1,
            x2,
            y2,
        )

        capture_time = time.perf_counter() - start

        print(
            f"Capture     : {capture_time:.3f} sec"
        )

        # ----------------------------------------------
        # Process Image
        # ----------------------------------------------

        result = self.process_image(region.image)

        if result["status"] == "success":
            self.translation_map.add_entry(
                region.bounds,
                result["original"],
                result["translation"],
            )

        result["capture_time"] = capture_time

        return result

    def get_translation_map(self):
        """
        Return the application's Translation Map.
        """

        return self.translation_map

    # --------------------------------------------------
    # LIVE MODE
    # --------------------------------------------------

    def start_live_mode(self):
        """
        Start the Desktop Observer.
        """

        self.desktop_observer.start()

    def stop_live_mode(self):
        """
        Stop the Desktop Observer.
        """

        self.desktop_observer.stop()

    def on_desktop_changed(
        self,
        dirty_regions,
    ):
        """
        Called by the Desktop Observer whenever the
        desktop changes.

        This is the future entry point for the
        Live Translation pipeline.
        """

        logger.info(
            "Desktop changed (%d dirty region(s)).",
            len(dirty_regions),
        )

        # Future pipeline:
        #
        # for region in dirty_regions:
        #     capture
        #     OCR
        #     translate
        #     update TranslationMap

    # ----------------------------------------------
    # TOOLS
    # ----------------------------------------------

    def show_history(self):

        logger.info(
            "TOOLS",
            "History selected"
        )

        messagebox.showinfo(
            "History",
            "History window will be implemented in the next phase."
        )

    def show_log_viewer(self):

        logger.info(
            "TOOLS",
            "Log Viewer selected"
        )

        messagebox.showinfo(
            "Log Viewer",
            "Log Viewer will be implemented in the next phase."
        )