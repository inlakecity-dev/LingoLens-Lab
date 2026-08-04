"""
LingoLens Application Controller

Coordinates every workflow inside LingoLens.

The Controller is the single system coordinator.

Responsibilities
----------------
• Owns the image processing pipeline.
• Owns Live Mode.
• Owns the TranslationMap.
• Supplies visible translations to the Floating Lens.
• Coordinates DesktopObserver.
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
    Central coordinator for the LingoLens application.

    The Controller is the only component allowed to
    coordinate OCR, Translation, History, Live Mode,
    Desktop Observer and the Translation Map.
    """

    def __init__(self, app_settings):

        self.app_settings = app_settings

        # ----------------------------------------------
        # Core Components
        # ----------------------------------------------

        # Single source of truth for the active desktop.
        self.translation_map = TranslationMap()

        # Live Desktop Observer.
        self.desktop_observer = DesktopObserver(self)

    # --------------------------------------------------
    # IMAGE PROCESSING PIPELINE
    # --------------------------------------------------

    def process_image(self, image):
        """
        Process an image through the OCR,
        Translation and History pipeline.

        This shared pipeline is used by every
        workflow that requires image processing.

        The caller is responsible for deciding
        what should happen with the returned result.
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
            self.app_settings.enabled_ocr_languages,
        )

        ocr_time = time.perf_counter() - start

        print(f"OCR         : {ocr_time:.3f} sec")

        if not original_text.strip():

            total_time = time.perf_counter() - total_start

            print(f"TOTAL       : {total_time:.3f} sec\n")

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

        print(f"Translation : {translation_time:.3f} sec")

        # ----------------------------------------------
        # History
        # ----------------------------------------------

        start = time.perf_counter()

        history_file = save_translation(
            original_text,
            translated_text,
            source_language,
            target_language,
        )

        history_time = time.perf_counter() - start

        print(f"History     : {history_time:.3f} sec")

        total_time = time.perf_counter() - total_start

        print("-" * 35)
        print(f"TOTAL       : {total_time:.3f} sec\n")

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

    # --------------------------------------------------
    # MANUAL TRANSLATION
    # --------------------------------------------------

    def translate_region(
        self,
        x1,
        y1,
        x2,
        y2,
    ):
        """
        Capture a user-selected region and process it
        through the shared image processing pipeline.

        Manual Translation and Live Translation both
        reuse the same processing pipeline.
        """

        # ----------------------------------------------
        # Capture selected region
        # ----------------------------------------------

        start = time.perf_counter()

        region = capture_region(
            x1,
            y1,
            x2,
            y2,
        )

        capture_time = time.perf_counter() - start

        print(f"Capture     : {capture_time:.3f} sec")

        # ----------------------------------------------
        # Process Image
        # ----------------------------------------------

        result = self.process_image(region.image)

        # ----------------------------------------------
        # Update Translation Map
        # ----------------------------------------------

        if result["status"] == "success":

            self.translation_map.add_entry(
                region.bounds,
                result["original"],
                result["translation"],
            )

        result["capture_time"] = capture_time

        return result

    # --------------------------------------------------
    # LIVE MODE
    # --------------------------------------------------

    def start_live_mode(self):
        """
        Start Live Translation.

        This starts the Desktop Observer.
        """

        logger.info(
            "LIVE",
            "Starting Live Mode."
        )

        self.desktop_observer.start()

    def stop_live_mode(self):
        """
        Stop Live Translation.
        """

        logger.info(
            "LIVE",
            "Stopping Live Mode."
        )

        self.desktop_observer.stop()

    def on_desktop_changed(
        self,
        dirty_regions,
    ):
        """
        Called by the Desktop Observer whenever the
        Windows desktop changes.

        DesktopObserver only reports dirty regions.

        The Controller owns the complete
        Live Translation pipeline.
        """

        logger.info(
            "DESKTOP",
            f"Desktop changed ({len(dirty_regions)} dirty region(s))."
        )

        for bounds in dirty_regions:

            # ------------------------------------------
            # Remove outdated translations
            # ------------------------------------------

            remove_method = getattr(
                self.translation_map,
                "remove_entries_in_region",
                None,
            )

            if callable(remove_method):
                remove_method(bounds)

            # ------------------------------------------
            # Capture updated desktop region
            # ------------------------------------------

            region = capture_region(*bounds)

            # ------------------------------------------
            # Shared processing pipeline
            # ------------------------------------------

            result = self.process_image(region.image)

            if result["status"] != "success":
                continue

            # ------------------------------------------
            # Update Translation Map
            # ------------------------------------------

            self.translation_map.add_entry(
                region.bounds,
                result["original"],
                result["translation"],
            )

    # --------------------------------------------------
    # FLOATING LENS
    # --------------------------------------------------

    def on_lens_moved(
        self,
        bounds,
    ):
        """
        Called whenever the Floating Lens moves.

        The Floating Lens only reports its
        desktop position.

        The Controller determines which
        translations are visible.
        """

        return self.get_visible_translations(bounds)

    def get_visible_translations(
        self,
        bounds,
    ):
        """
        Return every translation visible inside
        the supplied desktop region.

        This is the ONLY supported way for the
        Floating Lens to obtain translation data.

        The TranslationMap is never exposed to
        the UI.
        """

        return self.translation_map.get_entries_in_region(
            bounds
        )

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